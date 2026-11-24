"""
Notifications by e-mail and webhooks (Teams, Slack, JSON) for the events of the hooks (docs/features/notifications.md).

* etc/notifications.json: the channels (where a message goes) and the rules (which event, workflow and stage goes to
  which channel and recipients).
* `notify` is called by hooks.emit, also in the run of a stage. It only writes the message to the outbox (table
  notifications): a stage never waits for a mail server, and an error never fails it.
* A thread of the process sends it. A failed send is tried again after RETRY_DELAYS. The processes which run for long
  (web app, processing service) also send what a job process couldn't send before it ended.
* A message has only the values of get_message: no secrets of the deployment, custom data only with the fields of the rule.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests

from etc import constants
from modules import current_user, files, hooks, json_path
from modules.db import notification_data

if TYPE_CHECKING:
    from modules.meta_file import Meta_File
    from modules.stages import Stage


EVENTS = [event.value for event in hooks.Event]

# Seconds until the next attempt after the 1st, 2nd, 3rd failed one. Then the message has failed.
RETRY_DELAYS = [60, 300, 900]
# The sender looks for messages to send again (and for those of ended job processes)
POLL_SECONDS = 30
# Sent and failed messages are removed after these days
KEEP_DAYS = 30
DEFAULT_TIMEOUT_SECONDS = 15
# A job process waits at most this long for its messages before it ends
FLUSH_SECONDS = 20

CHANNEL_TYPES = ('email', 'webhook')
WEBHOOK_FORMATS = ('teams', 'slack', 'json')
TLS_MODES = ('starttls', 'ssl', 'none')
DEFAULT_PORTS = {'starttls': 587, 'ssl': 465, 'none': 25}

CREATOR = '@creator'
RUNNER = '@runner'
ROLE_PREFIX = '@role:'
MAIL_ADDRESS = re.compile(r"[^@\s<>,;:\"'()\[\]\\]+@[^@\s<>,;:\"'()\[\]\\]+")

TITLES = {
    'deployment_created': 'Deployment created',
    'deployment_finished': 'Deployment finished',
    'deployment_canceled': 'Deployment canceled',
    'stage_started': 'Stage {stage} started',
    'stage_finished': 'Stage {stage} finished',
    'stage_failed': 'Stage {stage} failed',
    'scheduled_run_failed': "Scheduled run of stage {stage} didn't start",
    'custom_data_changed': 'Custom data changed',
    'approval_requested': 'Stage {stage} needs an approval',
    'test': 'Test message',
}

FILE_KEYS = {'$schema', 'description', 'channels', 'rules'}
EMAIL_KEYS = {'type', 'description', 'host', 'port', 'tls', 'sender', 'user', 'password', 'password_env', 'timeout_seconds'}
WEBHOOK_KEYS = {'type', 'description', 'url', 'format', 'timeout_seconds'}
RULE_KEYS = {'description', 'events', 'workflows', 'stages', 'channel', 'recipients', 'custom_data'}



class Notification_Config_Error(Exception):
    """etc/notifications.json is invalid"""



class Notification_Error(Exception):
    """A message couldn't be sent. The text never contains the URL of a webhook (it's a secret)."""



#---------------------------------------------------------
# Configuration
#---------------------------------------------------------

class _Config:
    """Shared by the threads of a process, reloaded when the file changes"""
    lock = threading.Lock()
    file_hash: str|None = None
    config: dict|None = None
    error: str|None = None
    readable_by_others: bool = False



def load_config() -> dict|None:
    """
    The content of etc/notifications.json, validated.

    Returns:
        dict|None: None if there is no file or it's invalid (the error is logged once and shown on the settings page)
    """

    path = constants.C_NOTIFICATIONS_CONFIG

    if not os.path.isfile(path):
        with _Config.lock:
            _Config.file_hash, _Config.config, _Config.error, _Config.readable_by_others = None, None, None, False
        return None

    file_hash = files.get_file_hash(path)

    with _Config.lock:
        if file_hash != _Config.file_hash:
            _Config.file_hash, _Config.config, _Config.error = file_hash, None, None

            try:
                config = files.getJson(path, retry=True)
                validate(config)
                _Config.config = config
            except Exception as e:
                _Config.error = str(e)
                logging.error(f"Notifications are off: {path} is invalid: {e}")

            _Config.readable_by_others = is_readable_by_others(path)
            if _Config.readable_by_others:
                logging.warning(f"{path} can be read by other users, but it has passwords or webhook URLs: chmod 600 {path}")

        return _Config.config



def is_readable_by_others(path: str) -> bool:

    try:
        return os.name == 'posix' and bool(os.stat(path).st_mode & 0o044)
    except OSError:
        return False



def _fail(text: str):
    raise Notification_Config_Error(text)



def _check_keys(data: dict, allowed: set[str], where: str) -> None:

    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(f"{where}: unknown {'entries' if len(unknown) > 1 else 'entry'} {', '.join(repr(k) for k in unknown)} (allowed: {', '.join(sorted(allowed))})")



def _is_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ''



def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)



def validate(config) -> None:
    """
    Raises:
        Notification_Config_Error: With the first problem (channel or rule and what's wrong)
    """

    if not isinstance(config, dict):
        _fail("It has to be an object with 'channels' and 'rules'")

    _check_keys(config, FILE_KEYS, 'The file')

    channels = config.get('channels')
    if not isinstance(channels, dict) or not channels:
        _fail("'channels' has to be an object with at least one channel")

    for name, channel in channels.items():
        _validate_channel(name, channel)

    rules = config.get('rules', [])
    if not isinstance(rules, list):
        _fail("'rules' has to be a list")

    for number, rule in enumerate(rules, 1):
        _validate_rule(f"Rule {number}", rule, channels)



def _validate_channel(name: str, channel) -> None:

    where = f"Channel '{name}'"

    if not isinstance(channel, dict):
        _fail(f"{where} has to be an object")

    if channel.get('type') == 'email':
        _check_keys(channel, EMAIL_KEYS, where)

        if not _is_text(channel.get('host')):
            _fail(f"{where}: 'host' (the mail server) is missing")
        tls = channel.get('tls', 'starttls')
        if tls not in TLS_MODES:
            _fail(f"{where}: 'tls' has to be one of {', '.join(TLS_MODES)}")
        port = channel.get('port')
        if port is not None and (not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536):
            _fail(f"{where}: 'port' has to be a number from 1 to 65535")
        if not isinstance(channel.get('sender'), str) or not MAIL_ADDRESS.fullmatch(channel['sender']):
            _fail(f"{where}: 'sender' has to be an e-mail address")
        for key in ('user', 'password', 'password_env'):
            if key in channel and not isinstance(channel[key], str):
                _fail(f"{where}: '{key}' has to be a text")
        has_password = bool(channel.get('password') or channel.get('password_env'))
        if has_password and not channel.get('user'):
            _fail(f"{where}: 'password' needs 'user'")
        if has_password and tls == 'none':
            _fail(f"{where}: a password is never sent without TLS: set 'tls' to 'starttls' or 'ssl'")

    elif channel.get('type') == 'webhook':
        _check_keys(channel, WEBHOOK_KEYS, where)

        url = channel.get('url')
        parsed = urlparse(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme not in ('http', 'https') or not parsed.hostname:
            _fail(f"{where}: 'url' has to be an http or https URL")
        if channel.get('format') not in WEBHOOK_FORMATS:
            _fail(f"{where}: 'format' has to be one of {', '.join(WEBHOOK_FORMATS)}")

    else:
        _fail(f"{where}: 'type' has to be one of {', '.join(CHANNEL_TYPES)}")

    timeout = channel.get('timeout_seconds')
    if timeout is not None and (not _is_number(timeout) or timeout <= 0):
        _fail(f"{where}: 'timeout_seconds' has to be a number above 0")



def _validate_rule(where: str, rule, channels: dict) -> None:

    if not isinstance(rule, dict):
        _fail(f"{where} has to be an object")

    _check_keys(rule, RULE_KEYS, where)

    events = rule.get('events')
    if not isinstance(events, list) or not events or any(event not in EVENTS for event in events):
        _fail(f"{where}: 'events' has to be a list of these events: {', '.join(EVENTS)}")

    for key in ('workflows', 'stages'):
        if key in rule and (not isinstance(rule[key], list) or not all(_is_text(value) for value in rule[key])):
            _fail(f"{where}: '{key}' has to be a list of names")

    if rule.get('channel') not in channels:
        _fail(f"{where}: the channel '{rule.get('channel')}' doesn't exist in 'channels'")

    recipients = rule.get('recipients', [])
    if not isinstance(recipients, list) or not all(isinstance(r, str) for r in recipients):
        _fail(f"{where}: 'recipients' has to be a list")

    if channels[rule['channel']]['type'] == 'email':
        if not recipients:
            _fail(f"{where}: the e-mail channel '{rule['channel']}' needs 'recipients'")
        for recipient in recipients:
            if not (recipient in (CREATOR, RUNNER) or (recipient.startswith(ROLE_PREFIX) and recipient[len(ROLE_PREFIX):].strip())
                    or MAIL_ADDRESS.fullmatch(recipient)):
                _fail(f"{where}: the recipient '{recipient}' has to be an e-mail address, {CREATOR}, {RUNNER} or {ROLE_PREFIX}<name>")
    elif recipients:
        _fail(f"{where}: 'recipients' are only for e-mail channels: a webhook sends to its URL")

    custom_data = rule.get('custom_data', [])
    if not isinstance(custom_data, list):
        _fail(f"{where}: 'custom_data' has to be a list of JSONPaths")
    for path in custom_data:
        try:
            json_path.parse(path)
        except Exception as e:
            _fail(f"{where}: 'custom_data': {e}")



#---------------------------------------------------------
# Messages
#---------------------------------------------------------

def notify(event: hooks.Event|str, meta_file: Meta_File, stage: Stage|None=None, details: str|None=None) -> int:
    """
    Writes a message for each rule which matches the event to the outbox, and wakes the sender. It never raises.

    Returns:
        int: The number of messages
    """

    try:
        config = load_config()
        if config is None:
            return 0

        event = getattr(event, 'value', event)
        workflow = getattr(getattr(meta_file, 'workflow', None), 'name', None)
        user = current_user.get_user()
        rows = []

        for rule in config.get('rules', []):

            if not matches(rule, event, workflow, getattr(stage, 'name', None)):
                continue

            is_email = config['channels'][rule['channel']]['type'] == 'email'
            recipients = get_recipients(rule, meta_file, user) if is_email else []

            if is_email and not recipients:
                logging.info(f"Notification of '{event}' with channel {rule['channel']}: none of the recipients has an e-mail address")
                continue

            rows.append({'event': event, 'meta_file_id': meta_file.id, 'channel': rule['channel'], 'recipients': recipients,
                         'message': get_message(event, meta_file, stage, details, rule, user)})

        if not rows:
            return 0

        notification_data.add(rows)
        logging.info(f"Notification of '{event}' for deployment {meta_file.id}: {len(rows)} messages ({', '.join(row['channel'] for row in rows)})")
        start_sender()
        return len(rows)

    except Exception as e:
        logging.exception(f"Notification of '{event}' failed: {e}")
        return 0



def matches(rule: dict, event: str, workflow: str|None, stage: str|None) -> bool:
    """A rule with `stages` matches only the events of these stages"""

    if event not in rule['events']:
        return False
    if rule.get('workflows') and workflow not in rule['workflows']:
        return False
    if rule.get('stages') and stage not in rule['stages']:
        return False
    return True



def _value(status) -> Any:
    return getattr(status, 'value', status)



def get_message(event: str, mf: Meta_File, stage: Stage|None, details: str|None, rule: dict, user: str|None) -> dict:
    """The values of the deployment at the event. Custom data only with the fields of the rule."""

    custom_data = {}
    for path in rule.get('custom_data', []):
        value = json_path.get_value(mf.custom_data or {}, path)
        if value is not json_path.MISSING:
            custom_data[path] = value

    stage_name = getattr(stage, 'name', None)

    return {
        'event': event,
        'title': TITLES.get(event, event).format(stage=stage_name or '-'),
        'project': mf.project,
        'version': mf.deploy_version,
        'workflow': getattr(getattr(mf, 'workflow', None), 'name', None),
        'deployment_id': mf.id,
        'deployment_status': _value(mf.status),
        'stage': stage_name,
        'stage_status': _value(stage.status) if stage is not None else None,
        'user': user,
        'time': notification_data.now(),
        'url': get_url(f"/show_details/{mf.id}"),
        'details': details,
        'custom_data': custom_data,
    }



def get_url(path: str='') -> str|None:
    """Link to i-Releaser, None without C_EXTERNAL_URL"""

    base = (getattr(constants, 'C_EXTERNAL_URL', '') or '').rstrip('/')
    return f"{base}{path}" if base else None



def get_recipients(rule: dict, mf: Meta_File, user: str|None) -> list[str]:
    """The e-mail addresses of the rule; users (creator, runner, role) by their `mail` in user_permissions.json"""

    from modules import four_eyes, permission_config

    addresses = []

    for recipient in rule.get('recipients', []):

        if recipient == CREATOR:
            users = [four_eyes.get_creator(mf)]
        elif recipient == RUNNER:
            users = [user]
        elif recipient.startswith(ROLE_PREFIX):
            users = permission_config.get_users_of_role(recipient[len(ROLE_PREFIX):].strip())
        else:
            addresses.append(recipient)
            continue

        for name in users:
            mail = permission_config.get_mail(name)
            if mail and MAIL_ADDRESS.fullmatch(mail):
                addresses.append(mail)
            elif name:
                logging.info(f"User {name} has no e-mail address in {constants.C_USER_PERMISSIONS}: no notification for {recipient}")

    # Each address once
    unique = {}
    for address in addresses:
        unique.setdefault(address.lower(), address)
    return list(unique.values())



def get_facts(message: dict) -> list[tuple[str, str]]:
    """Label and value of the message, for all formats"""

    facts = [('Project', message.get('project')), ('Version', message.get('version')), ('Workflow', message.get('workflow'))]

    if message.get('stage'):
        facts.append(('Stage', f"{message['stage']} ({message.get('stage_status')})"))

    facts += [('Deployment', message.get('deployment_status')), ('User', message.get('user')), ('Time', format_time(message.get('time')))]

    return [(label, str(value)) for label, value in facts if value not in (None, '')]



def format_time(value: str|None) -> str|None:

    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value).astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    except ValueError:
        return value



def _as_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)



def get_subject(message: dict) -> str:

    name = ' '.join(str(v) for v in (message.get('project'), message.get('version')) if v not in (None, ''))
    subject = f"[i-Releaser] {message['title']}{': ' + name if name else ''}"
    # A header has one line
    return re.sub(r'[\r\n\t]+', ' ', subject)[:200]



def format_text(message: dict) -> str:
    """The text of an e-mail"""

    facts = get_facts(message)
    width = max((len(label) for label, _ in facts), default=0) + 1
    lines = [message['title'], '', *(f"{label + ':':<{width}} {value}" for label, value in facts)]

    if message.get('details'):
        lines += ['', message['details']]

    if message.get('custom_data'):
        lines += ['', 'Custom data:', *(f"  {path}: {_as_text(value)}" for path, value in message['custom_data'].items())]

    if message.get('url'):
        lines += ['', f"Open the deployment: {message['url']}" if message.get('deployment_id') else f"i-Releaser: {message['url']}"]

    lines += ['', '-- ', 'Sent by i-Releaser (rules in etc/notifications.json)']
    return '\n'.join(lines) + '\n'



def format_teams(message: dict) -> dict:
    """
    Adaptive Card for a Teams Workflows webhook ("When a Teams webhook request is received").
    The link is a text, not an action: some Workflows refuse cards with actions (HTTP 400).
    """

    body: list[dict] = [
        {'type': 'TextBlock', 'text': message['title'], 'weight': 'Bolder', 'size': 'Medium', 'wrap': True},
        {'type': 'FactSet', 'facts': [{'title': label, 'value': value} for label, value in get_facts(message)]},
    ]

    if message.get('details'):
        body.append({'type': 'TextBlock', 'text': message['details'], 'wrap': True})

    if message.get('custom_data'):
        body.append({'type': 'FactSet', 'facts': [{'title': path, 'value': _as_text(value)} for path, value in message['custom_data'].items()]})

    if message.get('url'):
        body.append({'type': 'TextBlock', 'text': f"[{'Open the deployment' if message.get('deployment_id') else 'i-Releaser'}]({message['url']})", 'wrap': True})

    card = {'$schema': 'http://adaptivecards.io/schemas/adaptive-card.json', 'type': 'AdaptiveCard', 'version': '1.4', 'body': body}

    return {'type': 'message', 'attachments': [{'contentType': 'application/vnd.microsoft.card.adaptive', 'contentUrl': None, 'content': card}]}



def _slack_escape(text) -> str:
    """Slack reads <...> as a link or a mention"""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')



def format_slack(message: dict) -> dict:
    """Message with blocks for a Slack incoming webhook"""

    blocks: list[dict] = [
        {'type': 'header', 'text': {'type': 'plain_text', 'text': message['title'][:150]}},
        # Slack allows 10 fields of 2000 characters
        {'type': 'section', 'fields': [{'type': 'mrkdwn', 'text': f"*{label}*\n{_slack_escape(value)}"[:2000]} for label, value in get_facts(message)[:10]]},
    ]

    more = []
    if message.get('details'):
        more.append(_slack_escape(message['details']))
    for path, value in (message.get('custom_data') or {}).items():
        more.append(f"*{_slack_escape(path)}*: {_slack_escape(_as_text(value))}")
    if message.get('url'):
        more.append(f"<{message['url']}|{'Open the deployment' if message.get('deployment_id') else 'i-Releaser'}>")

    if more:
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': '\n'.join(more)[:3000]}})

    return {'text': _slack_escape(get_subject(message)), 'blocks': blocks}



def format_json(message: dict) -> dict:
    return {'source': 'i-releaser', **message}



FORMATS = {'teams': format_teams, 'slack': format_slack, 'json': format_json}



#---------------------------------------------------------
# Sending
#---------------------------------------------------------

def send(channel: dict, message: dict, recipients: list[str]) -> None:
    """
    Raises:
        Notification_Error: It couldn't be sent
    """

    if channel['type'] == 'email':
        send_email(channel, message, recipients)
    else:
        send_webhook(channel, message)



def send_email(channel: dict, message: dict, recipients: list[str]) -> None:

    if not recipients:
        raise Notification_Error("No recipient")

    mail = EmailMessage()
    mail['Subject'] = get_subject(message)
    mail['From'] = channel['sender']
    mail['To'] = ', '.join(recipients)
    mail['Date'] = formatdate(usegmt=True)
    # The domain of the sender: without it, the name of the system is looked up (slow without DNS)
    mail['Message-ID'] = make_msgid(domain=channel['sender'].split('@')[-1])
    mail.set_content(format_text(message))

    tls = channel.get('tls', 'starttls')
    host = channel['host']
    port = channel.get('port') or DEFAULT_PORTS[tls]
    timeout = channel.get('timeout_seconds', DEFAULT_TIMEOUT_SECONDS)

    try:
        if tls == 'ssl':
            smtp = smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout)

        with smtp:
            if tls == 'starttls':
                smtp.starttls(context=ssl.create_default_context())
            if channel.get('user'):
                smtp.login(channel['user'], get_password(channel))
            smtp.send_message(mail)

    except (OSError, smtplib.SMTPException) as e:
        raise Notification_Error(f"Mail server {host}:{port}: {type(e).__name__}: {e}") from None



def get_password(channel: dict) -> str:
    """`password_env`: the name of an environment variable with the password (better than the password in the file)"""

    if channel.get('password_env'):
        return os.environ.get(channel['password_env'], '')
    return channel.get('password', '')



def send_webhook(channel: dict, message: dict) -> None:

    host = urlparse(channel['url']).hostname
    timeout = channel.get('timeout_seconds', DEFAULT_TIMEOUT_SECONDS)

    try:
        # No redirect: the message only goes to the configured URL
        r = requests.post(channel['url'], json=FORMATS[channel['format']](message), timeout=(5, timeout), allow_redirects=False)
    except requests.RequestException as e:
        # Not the text of the exception: it contains the URL, whose path is the secret of a webhook
        raise Notification_Error(f"Webhook {host}: {type(e).__name__}") from None

    if not 200 <= r.status_code < 300:
        raise Notification_Error(f"Webhook {host}: HTTP {r.status_code} {r.text[:200]}")



def deliver_due(limit: int=20) -> int:
    """
    Sends the messages of the outbox which are due. A failed one is tried again later, after the last attempt it has failed.

    Returns:
        int: The number of messages which have been tried
    """

    config = load_config()
    if config is None:
        return 0

    rows = notification_data.claim_due(limit)

    for row in rows:
        channel = config['channels'].get(row['channel'])

        try:
            if channel is None:
                raise Notification_Error(f"The channel '{row['channel']}' doesn't exist anymore in {constants.C_NOTIFICATIONS_CONFIG}")

            send(channel, row['message'], row['recipients'])
            notification_data.mark_sent(row['id'])
            logging.info(f"Notification {row['id']} ('{row['event']}', channel {row['channel']}) sent")

        except Exception as e:
            error = str(e)[:500]
            attempts = row['attempts'] + 1

            if attempts > len(RETRY_DELAYS) or channel is None:
                notification_data.mark_failed(row['id'], attempts, error)
                logging.error(f"Notification {row['id']} ('{row['event']}', channel {row['channel']}) failed {attempts} times, it's not sent: {error}")
            else:
                notification_data.mark_retry(row['id'], attempts, RETRY_DELAYS[attempts - 1], error)
                logging.warning(f"Notification {row['id']} ('{row['event']}', channel {row['channel']}) failed, tried again in {RETRY_DELAYS[attempts - 1]} seconds: {error}")

    return len(rows)



class _Sender:
    """The thread of this process which sends the outbox"""
    lock = threading.Lock()
    thread: threading.Thread|None = None
    wake = threading.Event()
    idle = threading.Event()
    enabled = True



def disable_sender() -> None:
    """
    For the main process of the processing service: it forks the job processes, and a fork of a process with threads
    may hang. Its messages wait in the outbox for the sender of the web app (at most POLL_SECONDS).
    A thread which runs already ends after its current round.
    """

    _Sender.enabled = False
    _Sender.wake.set()



def start_sender() -> None:
    """Starts the thread which sends the messages (once per process), and wakes it"""

    if not _Sender.enabled:
        return

    with _Sender.lock:
        if _Sender.thread is None or not _Sender.thread.is_alive():
            _Sender.idle.set()
            _Sender.thread = threading.Thread(target=_run_sender, name='notifications', daemon=True)
            _Sender.thread.start()

    _Sender.wake.set()



def _run_sender() -> None:

    while _Sender.enabled:
        _Sender.wake.clear()
        _Sender.idle.clear()

        try:
            while deliver_due() > 0:
                pass
        except Exception as e:
            # E.g. a locked database: the next round tries again
            logging.exception(f"Sending the notifications failed: {e}")
        finally:
            _Sender.idle.set()

        _Sender.wake.wait(POLL_SECONDS)



def flush(timeout: float=FLUSH_SECONDS) -> None:
    """
    Before a process ends (a job process): sends what is due now and waits for the thread.
    What fails is sent again by a process which runs longer.
    """

    end = time.monotonic() + timeout

    try:
        while time.monotonic() < end:
            tried = deliver_due(limit=5)
            idle = _Sender.idle.wait(max(0, end - time.monotonic())) if _Sender.thread is not None else True
            if tried == 0 and idle:
                return
    except Exception as e:
        logging.exception(f"Sending the notifications failed: {e}")



def _after_fork_in_child() -> None:
    """A forked process (a job of the processing service) has no thread of its parent"""

    _Sender.lock = threading.Lock()
    _Sender.thread = None
    _Sender.wake = threading.Event()
    _Sender.idle = threading.Event()
    _Sender.enabled = True
    _Config.lock = threading.Lock()



if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork_in_child)



#---------------------------------------------------------
# Settings page
#---------------------------------------------------------

def send_test(channel_name: str, recipient: str|None=None, user: str|None=None) -> str:
    """
    Sends a test message now (not with the outbox).

    Args:
        recipient (str, optional): For an e-mail channel. Default: the address of the user.

    Returns:
        str: Where it has been sent to (address or host)

    Raises:
        Notification_Config_Error: No (valid) configuration, no channel of this name, no address
        Notification_Error: It couldn't be sent
    """

    config = load_config()
    if config is None:
        raise Notification_Config_Error(_Config.error or f"There is no {constants.C_NOTIFICATIONS_CONFIG}")

    channel = config['channels'].get(channel_name)
    if channel is None:
        raise Notification_Config_Error(f"There is no channel '{channel_name}'")

    message = {'event': 'test', 'title': TITLES['test'], 'user': user, 'time': notification_data.now(), 'url': get_url(),
               'details': f"A test of the channel '{channel_name}' of i-Releaser. If you can read it, the channel works."}

    if channel['type'] != 'email':
        send(channel, message, [])
        return urlparse(channel['url']).hostname or ''

    from modules import permission_config

    address = (recipient or '').strip() or permission_config.get_mail(user)
    if not MAIL_ADDRESS.fullmatch(address):
        raise Notification_Config_Error("Enter the e-mail address for the test")

    send(channel, message, [address])
    return address



def get_status() -> dict:
    """For the settings page: the file, its problems, the channels (without secrets) and the outbox"""

    config = load_config()
    channels = []

    for name, channel in (config or {}).get('channels', {}).items():

        if channel['type'] == 'email':
            tls = channel.get('tls', 'starttls')
            destination = f"{channel['host']}:{channel.get('port') or DEFAULT_PORTS[tls]} ({tls}), from {channel['sender']}"
        else:
            # Only the host: the path of the URL is the secret of the webhook
            destination = f"{channel['format']}, {urlparse(channel['url']).hostname}"

        rules = sum(1 for rule in config.get('rules', []) if rule['channel'] == name)
        channels.append({'name': name, 'type': channel['type'], 'destination': destination, 'rules': rules})

    return {
        'file': constants.C_NOTIFICATIONS_CONFIG,
        'exists': os.path.isfile(constants.C_NOTIFICATIONS_CONFIG),
        'error': _Config.error,
        'readable_by_others': _Config.readable_by_others,
        'channels': channels,
        'outbox': notification_data.get_summary(KEEP_DAYS),
    }
