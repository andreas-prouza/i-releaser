# Glossary

Abbreviations and technical terms of i-Releaser and its documentation.
The terms of a deployment (workflow, stage, step, ...) are explained in more detail in [concepts](concepts.md#terms).

Each implementation adds the abbreviations and terms it introduces.

* [Abbreviations](#abbreviations)
* [Terms](#terms)


## Abbreviations

| Abbreviation | Meaning |
|---|---|
| API | Application Programming Interface. Here mostly the [Web API](webapi.md) of i-Releaser |
| CCSID | Coded Character Set Identifier: the character encoding of data on IBM i |
| CI | Continuous Integration: the tests run for every push (`.github/workflows/tests.yml`) |
| CL | Control Language: the command language of IBM i (e.g. `CRTLIB`). `cl` runs a CL command from PASE |
| CORS | Cross-Origin Resource Sharing: which other web sites may call the Web API from a browser |
| CSP | Content-Security-Policy: HTTP header which tells the browser which scripts and styles a page may load (see [technical notes](technik.md#content-security-policy)) |
| CSRF | Cross-Site Request Forgery: another web site makes the browser of a logged-in user send a request (see [technical notes](technik.md#csrf)) |
| DB | Database. i-Releaser's own database is SQLite (`var/app.sqlite`); the [DB deployment](db-deployment.md) works on Db2 for i |
| DDS | Data Description Specifications: the older way to describe files (tables, logical files) on IBM i |
| DST | Daylight Saving Time. Times of [scheduled runs](processing-service.md#scheduled-runs) are stored in UTC, so it can't move them |
| HSTS | HTTP Strict Transport Security: the browser uses only https for the site |
| IFS | Integrated File System: the directory tree of IBM i (`/home/...`), beside the libraries of `QSYS` |
| IPL | Initial Program Load: the start (restart) of an IBM i |
| ISO 8601 | Standard format of dates and times, e.g. `2026-11-24T22:00:00+01:00` (with time zone offset) |
| JSON | JavaScript Object Notation: the format of the workflow files, the custom data and the Web API |
| OBI | Object Builder for IBM i: builds the objects of a repository. Its build list (`compiles`) can be sent to i-Releaser as [compile list](webapi.md#create-a-deployment) |
| ODBC | Open Database Connectivity: the connection to Db2 for i used by the [DB deployment](db-deployment.md) |
| PASE | Portable Application Solutions Environment: the AIX/Unix environment of IBM i (bash, Python). Command type `PASE` of a [step action](workflow.md#commands) |
| PID | Process ID, e.g. of the processing service (`var/processing-service.pid`) |
| QSYS | The library system of IBM i. Command type `QSYS` of a [step action](workflow.md#commands): a CL command |
| RRN | Relative Record Number: position of a record in a table on IBM i. Used by the [DB deployment](db-deployment.md) to copy changes |
| SAVF | Save file: an IBM i file which holds saved objects (`CRTSAVF`, `SAVOBJ`, `RSTOBJ`) |
| SQL | Structured Query Language |
| SSE | Server-Sent Events: a connection on which the server pushes messages to the browser. Used by the [live updates](features/web-ui-live-updates.md) (`/api/watch_state`) |
| SSH | Secure Shell: runs `QSYS` commands on another IBM i (`execute_remote`) |
| SSRF | Server-Side Request Forgery: a request makes the server call another address |
| UAT | User Acceptance Test: a test stage of a workflow |
| UI | User Interface: the web app |
| UTC | Coordinated Universal Time: time without time zone and daylight saving time. `run_at` of a scheduled run is stored in UTC |
| WAL | Write-Ahead Log: mode of the SQLite database; `var/app.sqlite-wal` and `-shm` belong to `var/app.sqlite` |
| XSS | Cross-Site Scripting: script code from data which runs in the browser of another user |


## Terms

| Term | Meaning |
|---|---|
| Action history | History of a deployment: who did what when (run, schedule, cancel, reset, ...). Table `processing_users`, tab `Actions` of the deployment page |
| Attention bar | Bar on top of the deployment page: what the deployment waits for (failed, running, queued, scheduled or ready stage) with its buttons |
| Check error | `check_error` of a [step action](workflow.md#step-actions): if the step fails, the stage stops |
| Compile list | `compiles` of an OBI build list, stored with a deployment, see [concepts](concepts.md#terms) |
| Custom data | Any JSON stored with a deployment, see [concepts](concepts.md#terms) |
| Deploy object | An object of a deployment (library, name, type, attribute), see [concepts](concepts.md#terms) |
| Deployment | One run of a workflow. Called *meta file* in the code and the API |
| Four-eyes check | A second user has to approve before a stage runs ([feature](features/four-eyes-check.md), not implemented yet) |
| Heartbeat | Sign of life of a running job of the processing service, every `C_SERVICE_HEARTBEAT_INTERVAL` seconds |
| Hook | Python function of `scripts/` which a workflow runs on an event, e.g. `stage_failed`, see [workflow](workflow.md#hooks) |
| Job | One run of a stage by the processing service. Table `processing_jobs`, statuses `queued`, `running`, `finished`, `failed`, `canceled` |
| Live updates | The deployment page updates its parts when the deployment changes, without loading the page again |
| Meta file | The deployment (name in the code and the API) |
| Parallel group | Steps with the same `parallel_group` and `parallel: true` run at the same time, see [workflow](workflow.md#parallel-steps) |
| Parallel branches | A stage with several `next_stages`: the branches can run in any order, see [concepts](concepts.md#parallel-branches) |
| Placeholder | `{...}` in a command of a step, replaced by values of the deployment, see [workflow](workflow.md#placeholders) |
| Processing mode | `thread` (stages run in the web app) or `service` (stages run in the processing service) |
| Processing service | Own job which runs the stages, independent of the web app, see [processing service](processing-service.md) |
| Processing step | A named task of a stage, e.g. `save`, see [concepts](concepts.md#terms) |
| Queue | The jobs with status `queued`, waiting for the processing service |
| Run immediate | `run_immediate`: a stage runs by itself as soon as it becomes ready |
| Scheduled run | Run of a stage at a date and time (`Run at…`, `run_at`), see [processing service](processing-service.md#scheduled-runs) |
| Stage | A part of the workflow, usually an environment or phase (`BUILD`, `TEST`, `PROD`), see [concepts](concepts.md#terms) |
| Step (action) | The command of a processing step in a stage with its status and log; scripts can add sub-steps |
| Step action (mapping) | Maps a processing step to its command: `etc/default_step_action.json` or `step_action` of a workflow |
| Sub-step | A step added by a script while it runs, e.g. one `CRTSAVF` per library |
| Toast | Short message in the corner of a page after an action, which disappears by itself |
| Watchdog | Check of the web app every `C_SERVICE_WATCHDOG_INTERVAL` seconds that the processing service runs ([start automatically](processing-service.md#start-automatically)) |
| Workflow | The process of a deployment: stages, their order and steps. One JSON file in `etc/workflows/` |
