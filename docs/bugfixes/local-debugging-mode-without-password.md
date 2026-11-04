# Local debugging mode turns off the password check without notice

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

If the environment variable `I_RELEASER_LOCAL_DEBUGGING` is `true`, the login doesn't check the password ([app_login.py:28](../../webapp/web_modules/app_login.py#L28)).
Every user listed in `etc/user_permissions.json` can log in with any password.

* `python webapp/index.py` sets this variable automatically ([index.py:180](../../webapp/index.py#L180)).
* Nothing shows that the mode is on: no warning in the log, nothing in the web app.

If someone starts the web app this way on a server, or the variable is left in a service environment, the web app has no authentication.


## Requirements

1. `index.py` doesn't set the variable. Developers set it on purpose (e.g. in `.vscode/launch.json`).
2. When the mode is on:
   * the start writes a warning to the log;
   * the web app shows a banner on every page;
   * the web app only starts if it listens on `127.0.0.1`/`localhost` (see open questions).
3. Document the variable for developers (e.g. `CLAUDE.md` or a developer page).


## Acceptance criteria

- [x] Test: without the variable, `python webapp/index.py` checks the password.
- [x] Test: with the variable, the log contains a warning and the pages show the banner.
- [x] Test: with the variable and a bind address other than localhost the web app doesn't start.


## Non-goals

* A replacement login for tests


## Decisions

* Refuse to start or warn? **Refuse under gunicorn. Otherwise warning and banner.**
