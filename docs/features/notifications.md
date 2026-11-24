# Notifications (e-mail, Teams, Slack)

- **Status:** finished (2026-11-24; tested with `tests/test_notifications.py`, `tests/test_web_browser_notifications.py`. Not checked with a real Teams or Slack channel, not on IBM i)
- **Type:** feature
- **Priority:** P3
- **Source:** Code review 2026-11-23


## Current situation (before)

* Users see what happens only on the web page (live updates) or in Jira ([Jira integration](../jira.md)).
* [Hooks](../workflow.md#hooks) can run own scripts for the events of [hooks.py](../../modules/hooks.py) (`deployment_created`, `deployment_finished`, `deployment_canceled`, `stage_started`, `stage_finished`, `stage_failed`, `scheduled_run_failed`, `custom_data_changed`). Everyone who wants a mail has to write a script.
* A failed scheduled run at night, or a stage which waits for an approval ([four-eyes check](four-eyes-check.md)), is only noticed when someone looks.


## Requirements

1. Channels, configured in `etc/notifications.json` (template in `etc/examples/`):
   * `email`: SMTP server, port, TLS, sender, user/password (file `chmod 600`), with `smtplib` of the standard library;
   * `webhook`: URL and format `teams` (Adaptive Card), `slack` (blocks) or `json` (the event as JSON), with `requests` (exists).
2. Rules: event (the hook events plus `approval_requested` of the four-eyes check), optional workflow and stage, channel, recipients (e-mail addresses, or `@creator`, `@runner`, `@role:<name>` = users of a role; the e-mail address of a user is set on the user page).
3. Sending happens in the background (a thread with a queue), never in the run of a stage; a failed send is logged and tried again 3 times, it never fails a stage.
4. The message contains: project, version, workflow, stage, status, user, time, link to the deployment (`C_EXTERNAL_URL`).
5. A test button per channel on the settings page (admin).
6. No secrets of the deployment in the message (custom data only with fields listed in the rule).


## Acceptance criteria

- [x] Test: a failed stage sends one mail to a local SMTP test server (`smtpd` replacement in the test) with the right content. `test_failed_stage_sends_one_mail` (web app, thread mode), `test_job_process_of_the_service_sends` (processing service), `test_failed_stage_sends_a_mail_with_the_values_of_the_rule`
- [x] Test: a webhook with format `teams` posts the expected JSON to a local test server. `test_teams_webhook`
- [x] Test: an unreachable SMTP server doesn't change the result of the stage, and is tried again. `test_unreachable_mail_server_doesnt_change_the_stage`, `test_failed_send_is_tried_again`, `test_gives_up_after_the_last_attempt`
- [x] Test: `@role:<name>` sends to all users of the role with an e-mail address. `test_role_sends_to_all_users_of_the_role_with_an_address`


## Non-goals

* Notifications in the browser (push).
* Templates for the text in the web app (a file in `etc/` is enough).


## Set up

Copy the template and protect it: it has the password of the mail server and the URLs of the webhooks (whoever knows a webhook URL can post to the channel).

```sh
cp etc/examples/notifications.json etc/notifications.json
chmod 600 etc/notifications.json
```

```json
{
  "channels": {
    "mail": {"type": "email", "host": "smtp.example.com", "port": 587, "tls": "starttls",
             "sender": "i-releaser@example.com", "user": "i-releaser", "password_env": "I_RELEASER_SMTP_PASSWORD"},
    "teams": {"type": "webhook", "format": "teams", "url": "https://prod-00.westeurope.logic.azure.com/workflows/..."}
  },
  "rules": [
    {"events": ["stage_failed", "scheduled_run_failed"], "stages": ["PROD"], "channel": "mail",
     "recipients": ["@creator", "@runner", "@role:operators"], "custom_data": ["$.jira.ticket"]},
    {"events": ["approval_requested"], "channel": "mail", "recipients": ["@role:approvers"]},
    {"events": ["deployment_finished", "stage_failed"], "channel": "teams"}
  ]
}
```

**Channels**

| Attribute | Description |
|---|---|
| `type` | `email` or `webhook` |
| `host`, `port` | Mail server. Port default: 587 (`starttls`), 465 (`ssl`), 25 (`none`) |
| `tls` | `starttls` (default), `ssl` or `none`. A password is never sent with `none` (the file is refused) |
| `sender` | Address of the sender |
| `user`, `password` | Login at the mail server (optional). Better: `password_env`, the name of an environment variable with the password (set it for the web app and the processing service) |
| `url` | Webhook. Teams: a Workflow *"When a Teams webhook request is received"* (the old Office 365 connectors have been retired). Slack: an incoming webhook |
| `format` | `teams` (Adaptive Card), `slack` (blocks) or `json` (the values below as JSON, for own systems) |
| `timeout_seconds` | Maximum wait for the server, default 15 |

**Rules**

| Attribute | Description |
|---|---|
| `events` | The [events of the hooks](../workflow.md#hooks), plus `approval_requested` |
| `workflows`, `stages` | Only these (optional). A rule with `stages` only matches the events of a stage |
| `channel` | Name of a channel |
| `recipients` | E-mail channels only: addresses, `@creator` (who created the deployment), `@runner` (the user of the event: who ran the stage, canceled, changed the data), `@role:<name>` (all users of the role). The address of a user is `mail` in `etc/user_permissions.json` (*Mail* on the permissions page). Users without it are skipped |
| `custom_data` | JSONPaths of custom data which are in the message. Nothing else of the custom data is sent |

Every rule which matches sends a message: two rules for the same channel send two.
The file is checked when it changes; an invalid file turns the notifications off and is shown in the administration (`Administration` → `System` → `Notifications`) with the reason. There each channel has a button `Send test`.
In VS Code, `docs/schema/notifications.schema.json` checks the file while you type (see [workflow](../workflow.md#check-the-files-in-the-editor)).

**A message** has: title (e.g. *Stage PROD failed*), project, version, workflow, stage and its status, status of the deployment, user, time (UTC), the reason if there is one (e.g. why a scheduled run didn't start), the custom data of the rule, and the link to the deployment if `C_EXTERNAL_URL` is set.
Not in the message: other custom data, the output of the steps (it may contain anything a script prints).


## Decisions (2026-11-24)

* **Outbox instead of a queue in memory:** `notify` (called by `hooks.emit` after the hooks) writes each message to the table `notifications`; a thread of the process sends it. A job process of the processing service ends after its stage: a queue in its memory would be lost. The table also shows on the settings page what waits and what has failed.
* **Who sends:** the thread of the process which wrote the message, and in each worker of the web app a thread which looks every 30 seconds for messages to send again or left by an ended process. A message is claimed with one conditional update, so it's sent once; one which stays `sending` for 10 minutes (its process ended while sending) is sent again.
* **The processing service has no thread of the sender:** it forks the job processes, and a fork of a process with threads may hang. Its own messages (a job aborted by the service) wait for the web app. A job process sends its messages before it ends (at most 20 seconds), what fails is sent again by the web app.
* **Attempts:** after 1, 5 and 15 minutes; then the message has failed (logged as error, shown on the settings page). Sent and failed messages are removed after 30 days; the messages of a deployment are removed with it by the [data retention](data-retention.md).
* **E-mail address of a user:** the field `mail` of `etc/user_permissions.json`, which exists already and is set by an admin on the permissions page. Not a new field on the user page (the proposal of the open question): a second place for the same value.
* **Teams:** the format of the Workflows webhook (`{"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", ...}]}`, checked 2026-11-24). The link is a text of the card, not an action: users report that some Workflows refuse cards with actions (HTTP 400).
* **Secrets:** an error of a webhook shows only its host, never the URL (the URL's path is the secret); the settings page shows only the host too. The settings page warns if `etc/notifications.json` can be read by other users.
* **`approval_requested`** is sent when a stage with the [four-eyes check](four-eyes-check.md) becomes `ready` after the stage before it has finished and has no valid approval, and when its approval becomes invalid by a change. Also a hook event. A scheduled run which can't start for a missing approval sends `scheduled_run_failed` with the reason (the approval has been requested before).
* **`stage_failed` has no reason:** the error of a step is its output, which may contain anything a script prints. A job aborted by the processing service has its reason (e.g. no heartbeat).
* No new package: `smtplib` and `email` of the standard library, `requests` (exists). The tests have their own small mail server (`tests/notification_tools.py`): `smtpd` has been removed from Python 3.12.
* New error code `502` of the Web API: the test message was refused by the other server.


## Open questions (answered 2026-11-24)

* Is e-mail needed, or are Teams webhooks enough for the users? Teams retired the Office 365 connectors in favour of Workflows webhooks; the format has to be checked at implementation time. **Both**; the Workflows format is used.
* Where does the e-mail address of a user come from: user page, `user_permissions.json`, or the IBM i directory (`WRKDIRE`)? Proposal: user page. **`user_permissions.json`**, see decisions.
