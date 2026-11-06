# Bugfixes

One file per defect, with status, requirements, acceptance criteria and open questions (same way of working as `docs/features/`, see `CLAUDE.md`).
Found in the review of 2026-10-23. "Reproduced" means it was shown on a copy of the web app; "code review" means it was found in the code only.

> **Confidential:** files of type *security* describe how to exploit the defect.
> Don't push them to the public repository before the fix is released.

Priorities: **P0** fix first (exploitable or data loss) · **P1** high · **P2** medium · **P3** low


## Defects

| Priority | Defect | Type | Found by | Status |
|---|---|---|---|---|
| P0 | [Requests can run with the permissions of another user](current-user-shared-between-requests.md) | security | reproduced | finished |
| P0 | [Session takeover through the logs](session-takeover-via-logs.md) | security | reproduced | finished |
| P0 | [API token is stored in the custom data and logged](api-token-stored-in-custom-data.md) | security | reproduced | finished |
| P0 | [Parallel stages overwrite each other's progress](parallel-stages-lost-update.md) | bug | reproduced | finished |
| P0 | [Example deployment restores DB deployment tables over the new table](db-deployment-table-restored-over-new-table.md) | bug (data loss) | code review | ready |
| P1 | [Running a finished stage again blocks the deployment and the project](rerun-finished-stage-blocks-project.md) | bug | reproduced | finished |
| P1 | [Database updates depend on a config value and can make the start fail](db-migrations-rerun-on-every-start.md) | bug | reproduced | finished |
| P1 | [CORS allows any origin with credentials](cors-allows-any-origin.md) | security | reproduced | finished |
| P1 | [Actions can be triggered by a link (CSRF)](csrf-actions-via-get.md) | security | reproduced | finished |
| P1 | [QSYS and remote commands are changed by the shell](shell-quoting-of-commands.md) | security / bug | reproduced | ready |
| P1 | [Login: user and password unquoted in the ODBC connection string](login-connection-string-injection.md) | security | code review | ready |
| P1 | [Command placeholders: user input in shell commands, braces break commands](command-placeholders-with-user-input.md) | security / bug | code review | finished |
| P1 | [Missing permission checks](missing-permission-checks.md) | security | code review | finished |
| P1 | [Any custom data can be set when a deployment is created](custom-data-on-create-unrestricted.md) | security | code review | finished |
| P1 | [OBI can't start a workflow: build list larger than the custom data limit](compile-list-over-custom-data-limit.md) | bug (regression) | reproduced | finished |
| P1 | [DB deployment: names from custom data in CL commands unchecked](db-deployment-name-validation.md) | security | code review | finished |
| P1 | [API tokens are weak](weak-api-tokens.md) | security | code review | finished |
| P1 | [Session handling: unchecked session id, cookie flags, cleanup](session-store-hardening.md) | security | partly reproduced | finished |
| P1 | [Local debugging mode turns off the password check without notice](local-debugging-mode-without-password.md) | security | code review | finished |
| P1 | [Host header skips the login check](host-header-skips-login-check.md) | security | reproduced | finished |
| P1 | [Known vulnerabilities in dependencies](dependency-vulnerabilities.md) | security | `pip-audit` | ready |
| P2 | [`/api/list_deployments` fails if a deployment has custom data](list-deployments-fails-with-custom-data.md) | bug | reproduced | finished |
| P2 | [Object commands are never run](object-commands-never-run.md) | bug | reproduced | finished |
| P2 | [Command line `deployment.py` doesn't work](cli-deployment-py-broken.md) | bug | reproduced | finished |
| P2 | [Reset of a stage or deployment ignores running stages](reset-ignores-running-jobs.md) | bug | code review | finished |
| P2 | [Command output which isn't UTF-8 fails the step](command-output-decoding.md) | bug | code review | finished |
| P2 | [The exit code of a QSYS command gets lost](qsys-exit-code-lost.md) | bug | reproduced | ready |
| P2 | [SCRIPT steps capture the output of the whole process](script-step-output-capture.md) | bug | code review | finished |
| P2 | [Version numbers of deployments have gaps and can collide](deploy-version-numbering.md) | bug | code review | finished |
| P2 | [Templates: example scripts and configuration files](example-scripts-and-configs.md) | bug | code review | finished |
| P3 | [Object list: any file on the server can be given](object-list-path-not-restricted.md) | security | code review | finished |
| P3 | [Start script of the web app](webapp-service-script.md) | bug | code review | finished |
| P3 | [Minor code defects](minor-code-defects.md) | bug | code review | finished |


## Related improvements (`docs/features/`)

| Priority | Improvement | Status |
|---|---|---|
| P1 | [Tests in the repository](../features/tests-in-repository.md) | ready |
| P2 | [One invalid workflow file must not stop the web app](../features/workflow-file-error-isolation.md) | finished |
| P2 | [Finish stages without steps automatically](../features/auto-finish-stages-without-steps.md) | finished |
| P2 | [Back up the database before updates](../features/db-backup-before-update.md) | finished |
| P2 | [Timeout for commands](../features/command-timeout.md) | finished |
| P3 | [Consistent Web API responses](../features/api-consistency.md) | finished |
| P3 | [No blocking work in async handlers](../features/performance-blocking-handlers.md) | finished |
| P3 | [Configurable error handling for output on stderr](../features/step-stderr-handling.md) | finished |
| P3 | [Local settings in an untracked file](../features/local-settings-file.md) | finished |
| P3 | [Four-eyes check (and the permission `deploy`)](../features/four-eyes-check.md) | draft |
| P3 | [Remove dead code and unused files](../features/dead-code-cleanup.md) | finished |


## Still open

* [Known vulnerabilities in dependencies](dependency-vulnerabilities.md): FastAPI 0.125 / starlette 0.50, install on IBM i to check.
* [Four-eyes check](../features/four-eyes-check.md): needs a definition.
* `ready`: implemented and tested, only the check on an IBM i (or the first CI run) is missing. See the status line of each file.
