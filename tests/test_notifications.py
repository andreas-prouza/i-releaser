"""Notifications by e-mail and webhooks (docs/features/notifications.md)"""
import copy, json, os, sqlite3, time
from types import SimpleNamespace

import pytest

from notification_tools import SMTP_Server, Webhook_Server, wait_for
from web_server import USERS, WORKFLOWS, Web_Server, get_free_port

from etc import constants
# Before meta_file (circular import)
from modules import deploy_version  # noqa: F401
from modules import current_user, four_eyes, hooks, notifications, permission_config, retention
from modules.db import app_sqlite, notification_data
from modules.meta_file_status import Meta_file_status
from modules.stage_status import Status as Stage_Status


PERMISSIONS = {
    'users': {
        'boss': {'roles': ['ops'], 'permissions': {'general': ['admin'], 'workflows': {}}, 'detailed_infos': {'mail': 'boss@example.com'}},
        'anna': {'roles': ['OPS'], 'permissions': {'general': ['read'], 'workflows': {}}, 'detailed_infos': {'mail': 'anna@example.com'}},
        'nomail': {'roles': ['ops'], 'permissions': {'general': ['read'], 'workflows': {}}, 'detailed_infos': {'mail': ''}},
        'dev': {'roles': ['dev'], 'permissions': {'general': ['read'], 'workflows': {}}, 'detailed_infos': {'mail': 'dev@example.com'}},
    },
    'roles': {'ops': {'permissions': {'general': ['read']}}, 'dev': {'permissions': {'general': ['read']}}},
}

# The fixture `config` replaces it
START_SENDER = notifications.start_sender



#---------------------------------------------------------
# In the test process
#---------------------------------------------------------

@pytest.fixture()
def db(temp_db):
    """The database of the test (fixture temp_db of conftest.py)"""
    return os.path.join(temp_db, 'app.sqlite')


@pytest.fixture()
def users(tmp_path, monkeypatch):
    """user_permissions.json with e-mail addresses and roles"""

    path = tmp_path / 'user_permissions.json'
    path.write_text(json.dumps(PERMISSIONS))
    monkeypatch.setattr(constants, 'C_USER_PERMISSIONS', str(path))
    permission_config.PermissionKonfig.check_reload(force=True)
    yield
    monkeypatch.undo()
    permission_config.PermissionKonfig.check_reload(force=True)


@pytest.fixture()
def config(tmp_path, monkeypatch, db):
    """Writes etc/notifications.json. The thread of the sender isn't started: the tests send with deliver_due."""

    path = tmp_path / 'notifications.json'
    monkeypatch.setattr(constants, 'C_NOTIFICATIONS_CONFIG', str(path))
    monkeypatch.setattr(constants, 'C_EXTERNAL_URL', 'https://ireleaser.example.com')
    monkeypatch.setattr(notifications, 'start_sender', lambda: None)

    def write(data: dict) -> None:
        path.write_text(json.dumps(data))
        os.chmod(path, 0o600)

    return write


@pytest.fixture()
def smtp():
    server = SMTP_Server()
    yield server
    server.close()


@pytest.fixture()
def webhook():
    server = Webhook_Server()
    yield server
    server.close()


@pytest.fixture()
def user():
    token = current_user._current_user.set('BOSS')
    yield 'BOSS'
    current_user._current_user.reset(token)


def deployment() -> SimpleNamespace:
    return SimpleNamespace(id=7, project='shop', deploy_version=12, status=Meta_file_status.IN_PROCESS, workflow=SimpleNamespace(name='simple_wf'),
                           custom_data={'jira': {'ticket': 'ABC-1'}, 'password': 'secret-of-the-deployment'})


def stage(name: str='PROD', status: Stage_Status=Stage_Status.FAILED) -> SimpleNamespace:
    return SimpleNamespace(id=3, name=name, status=status)


def outbox() -> list[dict]:
    with app_sqlite.get_db_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM notifications ORDER BY id")]


def make_due() -> None:
    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET next_attempt_at = ?", (notification_data.now(-1),))
        conn.commit()



def test_the_example_is_valid():
    with open(os.path.join(constants.C_LOCAL_BASE_DIR, 'etc', 'examples', 'notifications.json')) as f:
        notifications.validate(json.load(f))


MAIL = {'type': 'email', 'host': 'smtp.example.com', 'sender': 'ir@example.com'}
HOOK = {'type': 'webhook', 'format': 'teams', 'url': 'https://hooks.example.com/x'}

@pytest.mark.parametrize('config, problem', [
    ([], "has to be an object"),
    ({'channels': {}}, "at least one channel"),
    ({'channels': {'m': MAIL}, 'rule': []}, "unknown entry 'rule'"),
    ({'channels': {'m': {**MAIL, 'type': 'sms'}}}, "'type' has to be one of"),
    ({'channels': {'m': {**MAIL, 'sender': 'nobody'}}}, "'sender' has to be an e-mail address"),
    ({'channels': {'m': {**MAIL, 'port': 0}}}, "'port'"),
    ({'channels': {'m': {**MAIL, 'user': 'u', 'password': 'p', 'tls': 'none'}}}, "never sent without TLS"),
    ({'channels': {'m': {**MAIL, 'password': 'p'}}}, "'password' needs 'user'"),
    ({'channels': {'m': {**MAIL, 'user': 'u', 'password_env': 'SMTP_PW', 'tls': 'none'}}}, "never sent without TLS"),
    ({'channels': {'h': {**HOOK, 'url': 'ftp://hooks.example.com/x'}}}, "http or https URL"),
    ({'channels': {'h': {**HOOK, 'format': 'xml'}}}, "'format'"),
    ({'channels': {'h': HOOK}, 'rules': [{'events': ['stage_exploded'], 'channel': 'h'}]}, "'events' has to be a list"),
    ({'channels': {'h': HOOK}, 'rules': [{'events': ['stage_failed'], 'channel': 'x'}]}, "channel 'x' doesn't exist"),
    ({'channels': {'h': HOOK}, 'rules': [{'events': ['stage_failed'], 'channel': 'h', 'recipients': ['a@example.com']}]}, "only for e-mail channels"),
    ({'channels': {'m': MAIL}, 'rules': [{'events': ['stage_failed'], 'channel': 'm'}]}, "needs 'recipients'"),
    ({'channels': {'m': MAIL}, 'rules': [{'events': ['stage_failed'], 'channel': 'm', 'recipients': ['@nobody']}]}, "has to be an e-mail address, @creator"),
    ({'channels': {'h': HOOK}, 'rules': [{'events': ['stage_failed'], 'channel': 'h', 'custom_data': ['$.a[x]']}]}, "'custom_data'"),
    ({'channels': {'h': HOOK}, 'rules': [{'events': ['stage_failed'], 'channel': 'h', 'stages': 'PROD'}]}, "'stages' has to be a list"),
])
def test_invalid_configuration(config, problem):

    with pytest.raises(notifications.Notification_Config_Error, match=problem):
        notifications.validate(config)



def test_an_invalid_file_turns_the_notifications_off(config, caplog):

    config({'channels': {}})

    assert notifications.load_config() is None
    assert 'at least one channel' in notifications.get_status()['error']
    assert notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage()) == 0



def test_rules_match_the_event_workflow_and_stage():

    rule = {'events': ['stage_failed'], 'workflows': ['simple_wf'], 'stages': ['PROD']}

    assert notifications.matches(rule, 'stage_failed', 'simple_wf', 'PROD')
    assert not notifications.matches(rule, 'stage_finished', 'simple_wf', 'PROD')
    assert not notifications.matches(rule, 'stage_failed', 'other_wf', 'PROD')
    assert not notifications.matches(rule, 'stage_failed', 'simple_wf', 'TEST')
    # A rule with stages: only the events of a stage
    assert not notifications.matches(rule, 'stage_failed', 'simple_wf', None)
    assert notifications.matches({'events': ['deployment_finished']}, 'deployment_finished', 'any_wf', None)



def test_failed_stage_sends_a_mail_with_the_values_of_the_rule(config, smtp, users, user):

    config({'channels': {'mail': smtp.channel()},
            'rules': [{'events': ['stage_failed'], 'channel': 'mail', 'recipients': ['@runner', 'ops@example.com'], 'custom_data': ['$.jira.ticket']}]})

    assert notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage(), details='Scheduled for 2026-11-24 21:00 UTC: missed') == 1
    assert notifications.deliver_due() == 1

    mail = smtp.wait_for(1)[0]
    assert mail['recipients'] == ['boss@example.com', 'ops@example.com']
    message = mail['message']
    assert message['Subject'] == '[i-Releaser] Stage PROD failed: shop 12'
    assert message['From'] == 'i-releaser@example.com'
    assert message['To'] == 'boss@example.com, ops@example.com'

    text = message.get_content()
    for expected in ['Stage PROD failed', 'Project:    shop', 'Version:    12', 'Workflow:   simple_wf', 'Stage:      PROD (failed)', 'Deployment: in process',
                     'User:       BOSS', 'Scheduled for 2026-11-24 21:00 UTC: missed', '$.jira.ticket: ABC-1',
                     'Open the deployment: https://ireleaser.example.com/show_details/7']:
        assert expected in text, expected
    # Only the custom data of the rule
    assert 'secret-of-the-deployment' not in message.as_string()

    assert outbox()[0]['status'] == 'sent'



def test_teams_webhook(config, webhook, user):

    config({'channels': {'teams': webhook.channel('teams')}, 'rules': [{'events': ['stage_finished'], 'channel': 'teams'}]})

    notifications.notify(hooks.Event.STAGE_FINISHED, deployment(), stage(status=Stage_Status.FINISHED))
    notifications.deliver_due()

    request = webhook.wait_for(1)[0]
    assert request['path'] == Webhook_Server.SECRET_PATH
    assert request['content_type'] == 'application/json'

    body = request['body']
    assert body['type'] == 'message'
    assert len(body['attachments']) == 1
    attachment = body['attachments'][0]
    assert attachment['contentType'] == 'application/vnd.microsoft.card.adaptive'
    assert attachment['contentUrl'] is None

    card = attachment['content']
    assert card['type'] == 'AdaptiveCard' and card['version'] == '1.4'
    assert card['body'][0] == {'type': 'TextBlock', 'text': 'Stage PROD finished', 'weight': 'Bolder', 'size': 'Medium', 'wrap': True}
    facts = {fact['title']: fact['value'] for fact in card['body'][1]['facts']}
    assert facts['Project'] == 'shop' and facts['Version'] == '12' and facts['Stage'] == 'PROD (finished)' and facts['User'] == 'BOSS'
    assert card['body'][-1]['text'] == '[Open the deployment](https://ireleaser.example.com/show_details/7)'
    # No action: some Teams Workflows refuse it
    assert 'actions' not in card
    # No custom data without a field in the rule
    assert 'ABC-1' not in json.dumps(body)



def test_slack_and_json_formats(monkeypatch):

    monkeypatch.setattr(constants, 'C_EXTERNAL_URL', 'https://ireleaser.example.com')
    message = notifications.get_message('stage_failed', SimpleNamespace(**{**vars(deployment()), 'project': '<!channel> & co'}), stage(),
                                        'details <b>', {'custom_data': ['$.jira.ticket']}, 'BOSS')

    slack = notifications.format_slack(message)
    text = json.dumps(slack)
    # Slack reads <...> as a mention or a link
    assert '<!channel>' not in text and '&lt;!channel&gt; &amp; co' in text
    assert slack['blocks'][-1]['text']['text'] == 'details &lt;b&gt;\n*$.jira.ticket*: ABC-1\n<https://ireleaser.example.com/show_details/7|Open the deployment>'

    data = notifications.format_json(message)
    assert data['source'] == 'i-releaser' and data['event'] == 'stage_failed' and data['custom_data'] == {'$.jira.ticket': 'ABC-1'}



def test_role_sends_to_all_users_of_the_role_with_an_address(config, smtp, users):

    config({'channels': {'mail': smtp.channel()}, 'rules': [{'events': ['deployment_finished'], 'channel': 'mail', 'recipients': ['@role:ops']}]})

    notifications.notify(hooks.Event.DEPLOYMENT_FINISHED, deployment())
    notifications.deliver_due()

    # The role without case (anna has 'OPS'); nomail has no address, dev another role
    assert smtp.wait_for(1)[0]['recipients'] == ['anna@example.com', 'boss@example.com']



def test_creator_and_runner(config, smtp, users, monkeypatch):

    monkeypatch.setattr(four_eyes, 'get_creator', lambda mf: 'anna')
    config({'channels': {'mail': smtp.channel()},
            'rules': [{'events': ['deployment_canceled'], 'channel': 'mail', 'recipients': ['@creator', '@runner', 'Anna@example.com']}]})

    # Without a user (e.g. a thread of the service): only the creator; each address once
    notifications.notify(hooks.Event.DEPLOYMENT_CANCELED, deployment())
    notifications.deliver_due()

    assert smtp.wait_for(1)[0]['recipients'] == ['anna@example.com']



def test_no_message_without_a_recipient_with_an_address(config, users):

    config({'channels': {'mail': {**MAIL}}, 'rules': [{'events': ['stage_failed'], 'channel': 'mail', 'recipients': ['@runner']}]})

    assert notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage()) == 0
    assert outbox() == []



def test_failed_send_is_tried_again(config, smtp, monkeypatch):

    monkeypatch.setattr(notifications, 'RETRY_DELAYS', [60, 300, 900])
    config({'channels': {'mail': smtp.channel()}, 'rules': [{'events': ['stage_failed'], 'channel': 'mail', 'recipients': ['ops@example.com']}]})
    smtp.reject = 1

    notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage())
    assert notifications.deliver_due() == 1

    row = outbox()[0]
    assert row['status'] == 'pending' and row['attempts'] == 1 and '451' in row['last_error']
    # Not before its time
    assert row['next_attempt_at'] > notification_data.now(50)
    assert notifications.deliver_due() == 0

    make_due()
    assert notifications.deliver_due() == 1
    assert len(smtp.wait_for(1)) == 1
    assert outbox()[0]['status'] == 'sent'



def test_gives_up_after_the_last_attempt(config, monkeypatch):

    monkeypatch.setattr(notifications, 'RETRY_DELAYS', [0, 0, 0])
    config({'channels': {'mail': {**MAIL, 'host': '127.0.0.1', 'port': get_free_port(), 'tls': 'none'}},
            'rules': [{'events': ['stage_failed'], 'channel': 'mail', 'recipients': ['ops@example.com']}]})

    notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage())

    for _ in range(4):
        make_due()
        notifications.deliver_due()

    row = outbox()[0]
    assert row['status'] == 'failed' and row['attempts'] == 4 and 'Mail server 127.0.0.1' in row['last_error']
    assert notification_data.get_summary()['failed'] == 1
    assert notifications.deliver_due() == 0



def test_webhook_errors_dont_show_the_secret_of_the_url(config, webhook):

    closed = {'type': 'webhook', 'format': 'json', 'url': f"http://127.0.0.1:{get_free_port()}{Webhook_Server.SECRET_PATH}"}
    with pytest.raises(notifications.Notification_Error) as error:
        notifications.send(closed, {'title': 'x'}, [])
    assert '127.0.0.1' in str(error.value) and 'secret-token' not in str(error.value)

    webhook.status = 500
    with pytest.raises(notifications.Notification_Error, match='HTTP 500'):
        notifications.send(webhook.channel(), {'title': 'x'}, [])



def test_notify_never_raises(config, monkeypatch):

    config({'channels': {'hook': HOOK}, 'rules': [{'events': ['stage_failed'], 'channel': 'hook'}]})

    def broken(rows):
        raise sqlite3.OperationalError('database is locked')

    monkeypatch.setattr(notification_data, 'add', broken)
    assert notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage()) == 0



def test_a_message_is_claimed_once(db):

    notification_data.add([{'event': 'stage_failed', 'meta_file_id': 1, 'channel': 'c', 'message': {'title': 'x'}}])

    assert len(notification_data.claim_due()) == 1
    # Another process doesn't get it
    assert notification_data.claim_due() == []

    # A process which ended while sending it: it's sent again later
    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET claimed_at = ?", (notification_data.now(-notification_data.STALE_SECONDS - 1),))
        conn.commit()
    assert len(notification_data.claim_due()) == 1



def test_old_messages_are_removed(db):

    notification_data.add([{'event': 'stage_failed', 'meta_file_id': 1, 'channel': 'c', 'message': {}} for _ in range(3)])
    with app_sqlite.get_db_connection() as conn:
        conn.execute("UPDATE notifications SET status = 'sent', created_at = '2020-01-01T00:00:00+00:00' WHERE id IN (1, 2)")
        conn.execute("UPDATE notifications SET created_at = '2020-01-01T00:00:00+00:00' WHERE id = 3")
        conn.commit()

    # Not one which still waits
    assert notification_data.remove_older_than(30) == 2
    assert [row['id'] for row in outbox()] == [3]



def test_retention_removes_the_messages_of_a_deployment(db):

    notification_data.add([{'event': 'stage_failed', 'meta_file_id': 5, 'channel': 'c', 'message': {}},
                           {'event': 'stage_failed', 'meta_file_id': 6, 'channel': 'c', 'message': {}}])

    retention.remove({'id': 5, 'meta_dir': None})

    assert [row['meta_file_id'] for row in outbox()] == [6]



def test_sender_thread_sends(config, webhook, monkeypatch):

    config({'channels': {'hook': webhook.channel()}, 'rules': [{'events': ['stage_failed'], 'channel': 'hook'}]})
    monkeypatch.setattr(notifications, 'start_sender', START_SENDER)

    try:
        notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage())
        assert webhook.wait_for(1, timeout=5)[0]['body']['event'] == 'stage_failed'
        wait_for(lambda: [row for row in outbox() if row['status'] == 'sent'], 1, timeout=5)

    finally:
        # The thread ends: it must not send the messages of other tests
        notifications.disable_sender()
        notifications._Sender.thread.join(5)
        assert not notifications._Sender.thread.is_alive()
        notifications._Sender.thread = None
        notifications._Sender.enabled = True



def test_no_thread_when_the_sender_is_disabled(monkeypatch):

    monkeypatch.setattr(notifications._Sender, 'enabled', False)
    monkeypatch.setattr(notifications._Sender, 'thread', None)

    START_SENDER()
    assert notifications._Sender.thread is None



def test_flush_sends_what_is_due(config, webhook):

    config({'channels': {'hook': webhook.channel()}, 'rules': [{'events': ['stage_failed'], 'channel': 'hook'}]})

    notifications.notify(hooks.Event.STAGE_FAILED, deployment(), stage())
    notifications.flush(timeout=5)

    assert len(webhook.requests) == 1
    assert outbox()[0]['status'] == 'sent'



def test_settings_status_without_secrets(config, webhook, tmp_path):

    config({'channels': {'teams': webhook.channel('teams'), 'mail': {**MAIL, 'user': 'u', 'password': 'p'}},
            'rules': [{'events': ['stage_failed'], 'channel': 'teams'}]})
    os.chmod(constants.C_NOTIFICATIONS_CONFIG, 0o644)
    # Read again: the file is the same, only its permissions have changed
    notifications._Config.file_hash = None

    status = notifications.get_status()
    text = json.dumps(status)
    assert 'secret-token' not in text and '"p"' not in text
    assert {c['name']: c['destination'] for c in status['channels']} == {'teams': 'teams, 127.0.0.1', 'mail': 'smtp.example.com:587 (starttls), from ir@example.com'}
    assert status['channels'][0]['rules'] == 1
    if os.name == 'posix':
        assert status['readable_by_others']



def test_password_from_the_environment(monkeypatch):

    monkeypatch.setenv('I_RELEASER_TEST_SMTP_PASSWORD', 'from-env')
    assert notifications.get_password({'password': 'in-file', 'password_env': 'I_RELEASER_TEST_SMTP_PASSWORD'}) == 'from-env'
    assert notifications.get_password({'password': 'in-file'}) == 'in-file'



def test_send_test(config, smtp, webhook, users):

    config({'channels': {'mail': smtp.channel(), 'hook': webhook.channel('slack')}})

    assert notifications.send_test('mail', None, 'boss') == 'boss@example.com'
    assert notifications.send_test('mail', 'ops@example.com', 'boss') == 'ops@example.com'
    assert [m['recipients'] for m in smtp.wait_for(2)] == [['boss@example.com'], ['ops@example.com']]
    assert 'Test message' in smtp.messages[0]['message']['Subject']

    assert notifications.send_test('hook', None, 'boss') == '127.0.0.1'
    assert webhook.wait_for(1)[0]['body']['blocks'][0]['text']['text'] == 'Test message'

    with pytest.raises(notifications.Notification_Config_Error, match="no channel 'x'"):
        notifications.send_test('x')
    with pytest.raises(notifications.Notification_Config_Error, match='Enter the e-mail address'):
        notifications.send_test('mail', None, 'nomail')



#---------------------------------------------------------
# The web app (and the processing service) in their own processes
#---------------------------------------------------------

FAIL_WF = {
    'name': 'fail_wf',
    'default_project': 'fail',
    'step_action': [{'processing_step': 'fail', 'environment': 'PASE', 'execute': 'echo some output; false', 'check_error': True}],
    'stages': [
        {'name': 'START', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['fail']},
        {'name': 'END'},
    ],
}

EYES_WF = {
    'name': 'eyes_wf',
    'default_project': 'eyes',
    'editable_fields': ['$.ticket'],
    'step_action': [{'processing_step': 'quick', 'environment': 'PASE', 'execute': 'echo quick', 'check_error': True}],
    'stages': [
        {'name': 'START', 'next_stages': ['PROD'], 'host': 'localhost', 'processing_steps': ['quick']},
        {'name': 'PROD', 'next_stages': ['END'], 'host': 'localhost', 'processing_steps': ['quick'], 'four_eyes_check': True},
        {'name': 'END'},
    ],
}

TEAM = {
    **copy.deepcopy(USERS),
    'creator': {'permissions': {'general': ['read', 'start workflow', 'run', 'edit-custom-data'], 'workflows': {}}},
    'checker': {'permissions': {'general': ['read', 'run', '4-eyes check'], 'workflows': {}}},
}
TEAM['boss']['detailed_infos'] = {'mail': 'boss@example.com'}


def write_config(server: Web_Server, config: dict) -> None:
    path = server.path('etc', 'notifications.json')
    with open(path, 'w') as f:
        json.dump(config, f)
    os.chmod(path, 0o600)


def server_outbox(server: Web_Server) -> list[dict]:
    with sqlite3.connect(server.path('var', 'app.sqlite')) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM notifications ORDER BY id")]


@pytest.fixture(scope='module')
def mail_server():
    s = SMTP_Server()
    yield s
    s.close()


@pytest.fixture(scope='module')
def hook_server():
    s = Webhook_Server()
    yield s
    s.close()


@pytest.fixture(scope='module')
def app(mail_server, hook_server):

    s = Web_Server(workflows={**WORKFLOWS, 'fail_wf': FAIL_WF, 'eyes_wf': EYES_WF}, users=TEAM,
                   settings="C_EXTERNAL_URL = 'https://ireleaser.example.com'\n")
    write_config(s, {
        'channels': {
            'mail': mail_server.channel(),
            'down': {**mail_server.channel(), 'port': get_free_port()},
            'hook': hook_server.channel('json'),
        },
        'rules': [
            {'events': ['stage_failed'], 'workflows': ['fail_wf'], 'channel': 'mail', 'recipients': ['@runner', 'ops@example.com'], 'custom_data': ['$.ticket']},
            {'events': ['stage_finished'], 'workflows': ['seq_wf'], 'stages': ['START'], 'channel': 'down', 'recipients': ['ops@example.com']},
            {'events': ['approval_requested'], 'channel': 'hook'},
        ],
    })
    s.start()
    yield s
    s.close()



def test_failed_stage_sends_one_mail(app, mail_server):

    boss = app.client('boss')
    deployment = boss.create_deployment('fail_wf', {'ticket': 'ABC-1', 'token': 'secret-of-the-deployment'})
    sent_before = len(mail_server.messages)

    assert boss.run_stage(deployment, 'START')[0] == 200
    assert boss.wait_for_stage(deployment, 'START', status=('failed',))['status'] == 'failed'

    mail = wait_for(lambda: mail_server.messages[sent_before:], 1)[0]
    assert mail['recipients'] == ['boss@example.com', 'ops@example.com']

    message = mail['message']
    assert message['Subject'].startswith('[i-Releaser] Stage START failed: fail ')
    text = message.get_content()
    assert 'Workflow:   fail_wf' in text and 'User:       BOSS' in text and '$.ticket: ABC-1' in text
    assert f"Open the deployment: https://ireleaser.example.com/show_details/{deployment}" in text
    # Neither other custom data nor the output of the step
    assert 'secret-of-the-deployment' not in message.as_string() and 'some output' not in message.as_string()

    # A time has to pass: no second mail comes
    time.sleep(1)
    assert len(mail_server.messages) == sent_before + 1



def test_unreachable_mail_server_doesnt_change_the_stage(app):

    boss = app.client('boss')
    deployment = boss.create_deployment('seq_wf')

    assert boss.run_stage(deployment, 'START')[0] == 200
    assert boss.wait_for_stage(deployment, 'START')['status'] == 'finished'
    # The next stage is ready: the run has gone on
    assert boss.get_stages(deployment)['PROD']['status'] == 'ready'

    # Tried once, tried again later
    rows = wait_for(lambda: [r for r in server_outbox(app) if r['meta_file_id'] == deployment and r['attempts'] == 1], 1)
    assert rows[0]['status'] == 'pending' and rows[0]['channel'] == 'down' and 'Mail server 127.0.0.1' in rows[0]['last_error']
    assert rows[0]['next_attempt_at'] > rows[0]['created_at']



def test_approval_requested(app, hook_server):

    creator = app.client('creator')
    deployment = creator.create_deployment('eyes_wf')

    assert creator.run_stage(deployment, 'START')[0] == 200
    creator.wait_for_stage(deployment, 'START')

    # PROD waits for the second person
    request = wait_for(lambda: [r for r in hook_server.requests if r['body']['deployment_id'] == deployment], 1)[0]
    assert request['body']['event'] == 'approval_requested' and request['body']['stage'] == 'PROD'
    assert request['body']['title'] == 'Stage PROD needs an approval' and request['body']['user'] == 'CREATOR'

    checker = app.client('checker')
    assert checker.post_json(f"/api/approve_stage/{deployment}/{creator.get_stages(deployment)['PROD']['id']}")[0] == 200

    # A change makes the approval invalid: it's requested again
    assert creator.post_json(f"/api/edit_custom_data/{deployment}", {'fields': {'$.ticket': 'ABC-2'}})[0] == 200
    requests = wait_for(lambda: [r for r in hook_server.requests if r['body']['deployment_id'] == deployment], 2)
    assert requests[1]['body']['event'] == 'approval_requested'
    assert 'The approval is no longer valid: custom data changed' in requests[1]['body']['details']



def test_settings_page_and_test_message(app, mail_server, hook_server):

    boss = app.client('boss')

    _, _, page = boss.get('/settings', headers={'Accept': 'text/html'})
    assert 'id="notifications-title"' in page
    assert page.count('data-action="test-notification"') == 3
    assert 'data-mail="boss@example.com"' in page
    # Only the host of a webhook: its path is the secret
    assert Webhook_Server.SECRET_PATH not in page and 'json, 127.0.0.1' in page

    sent_before = len(mail_server.messages)
    status, body = boss.post_json('/api/notifications/test/mail', {'recipient': 'ops@example.com'})
    assert status == 200 and body['sent_to'] == 'ops@example.com'
    assert wait_for(lambda: mail_server.messages[sent_before:], 1)[0]['recipients'] == ['ops@example.com']

    status, body = boss.post_json('/api/notifications/test/hook')
    assert status == 200 and body['sent_to'] == '127.0.0.1'
    assert any(r['body']['event'] == 'test' for r in hook_server.requests)

    assert boss.post_json('/api/notifications/test/down', {'recipient': 'ops@example.com'})[0] == 502
    assert boss.post_json('/api/notifications/test/nothing')[0] == 409
    assert app.client('intern').post_json('/api/notifications/test/mail', {'recipient': 'ops@example.com'})[0] == 403



def test_job_process_of_the_service_sends(mail_server):

    s = Web_Server(workflows={**WORKFLOWS, 'fail_wf': FAIL_WF}, users=TEAM, settings="C_SERVICE_WATCHDOG_INTERVAL = 1\n")
    s.write_app_settings({'C_PROCESSING_MODE': 'service', 'C_SERVICE_AUTO_START': True})
    write_config(s, {'channels': {'mail': mail_server.channel()},
                     'rules': [{'events': ['stage_failed'], 'channel': 'mail', 'recipients': ['@runner']}]})

    try:
        s.start()
        s.wait_for_service()

        boss = s.client('boss')
        deployment = boss.create_deployment('fail_wf')
        sent_before = len(mail_server.messages)

        assert boss.run_stage(deployment, 'START')[0] == 200
        boss.wait_for_stage(deployment, 'START', status=('failed',), timeout=30)

        mail = wait_for(lambda: mail_server.messages[sent_before:], 1)[0]
        assert mail['recipients'] == ['boss@example.com']
        assert server_outbox(s)[0]['status'] == 'sent'

        # The stage has run as a job of the service, and its process has sent the mail (not the web app)
        with sqlite3.connect(s.path('var', 'app.sqlite')) as conn:
            assert conn.execute("SELECT count(*) FROM processing_jobs WHERE meta_file_id = ?", (deployment,)).fetchone()[0] == 1
        with open(s.path('log', 'service.log'), errors='replace') as f:
            assert "Notification 1 ('stage_failed', channel mail) sent" in f.read()

    finally:
        s.close()
