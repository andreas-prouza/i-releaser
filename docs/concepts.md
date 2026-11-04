# Concepts

* [Terms](#terms)
* [Life of a deployment](#life-of-a-deployment)
* [Running a stage](#running-a-stage)
* [Status](#status)
* [Parallel branches](#parallel-branches)
* [One deployment after the other](#one-deployment-after-the-other)
* [Libraries and branches of a deployment](#libraries-and-branches-of-a-deployment)
* [Corrections](#corrections)
* [Where the data is stored](#where-the-data-is-stored)


## Terms

| Term | Meaning |
|---|---|
| Project | Groups deployments, e.g. of one application. Each project has its own version numbers. A workflow belongs to one project (`default_project`). |
| Workflow | The process of a deployment: its stages, their order and their steps. One JSON file in `etc/workflows/`. |
| Deployment | One run of a workflow, e.g. version 42 of project `erp`. It has a status, an object list, custom data and its history. (In the code and the API it's also called *meta file*.) |
| Stage | A part of the workflow, usually an environment or a phase: `START`, `BUILD`, `TEST`, `PROD`, `END`. A user runs a stage. |
| Processing step | A named task of a stage, e.g. `save` or `transfer`. Its command is defined in a [step mapping](workflow.md#step-actions). |
| Step (action) | The command of a processing step in a stage, with its status and log. Scripts may add sub-steps, e.g. one `CRTSAVF` per library. |
| Deploy object | An object of the deployment (production library, name, type, attribute). Imported from an [object list](workflow.md#object-list). |
| Custom data | Any JSON you store with a deployment, e.g. a ticket number. Set when the deployment is created; users can [edit](workflow.md#editable-custom-fields) the fields the workflow allows. |


## Life of a deployment

```
create ──► START ──► BUILD ──► TEST ──► PROD ──► END ──► finished
            run       run       run      run      run
```

1. **Create.** In the web app (`Workflows` → create) or with the [Web API](webapi.md#create-a-deployment).
   * The deployment gets the next version number of its project.
   * All stages of the workflow are created. `START` is `ready`, the others are `new`.
   * The workflow definition is stored with the deployment. Later changes of the workflow file only affect new deployments.
2. **Run a stage.** A user with the permission `run` starts a `ready` stage (button on the deployment page or the Web API).
3. **Stage finished.** When all its steps are finished, the stage is `finished` and its `next_stages` become `ready`.
   Next stages with `run_immediate` start right away.
4. **Deployment finished.** When all stages are finished, the deployment is `finished`.
   A stage without steps (usually `END`) finishes by itself as soon as it's reached and doesn't wait for other stages.
   So a deployment whose last stage has no steps is finished right after the last stage with steps, and that stage can't be [reset](workflow.md#reset-the-last-finished-stage) anymore.

A deployment can be canceled at any time (permission `cancel workflow`). A running stage is not stopped by that, but the deployment stays `canceled`.


## Running a stage

The steps of a stage run one after the other, in the order of `processing_steps` of the stage. Steps can also run at the same time, see [parallel steps](workflow.md#parallel-steps).

* **Command types**: `QSYS` (IBM i command), `PASE` (shell command) and `SCRIPT` (Python function), see [commands](workflow.md#commands).
* **Errors**: a `PASE` or `QSYS` step fails if its exit code isn't 0 *or* if it writes anything to stderr (unless [`fail_on_stderr`](workflow.md#step-actions) is `false`), or if it exceeds its timeout. A `SCRIPT` step fails if the function raises an exception.
* **Error check**: if a step with error check (`check_error: true`, the default) fails, the stage stops and is `failed`.
  A step without error check may fail; the stage continues.
  Users with the permission `change check error` can turn off the error check of a failed step, so the stage can continue.
* **Run again**: a failed stage can be run again:
  * `Continue` starts with the first step which isn't finished. A failed step without error check counts as done.
  * `Run all` runs all steps again.
* **Where it runs**: in a thread of the web app, or in its own process if the [processing service](processing-service.md) is used.
* **Who**: each run is recorded with the user who started it, and the steps' commands run under the user profile of i-Releaser.

Each run of a stage gets its own log (deployment page → history), and each step stores its stdout and stderr.


## Status

**Deployment**

| Status | Meaning |
|---|---|
| `new` | Being created |
| `ready` | Waiting for the next stage to be run |
| `in process` | A stage is running |
| `failed` | A stage has failed. Run it again (or another ready stage). |
| `finished` | All stages are finished |
| `canceled` | Canceled by a user. Nothing can be run anymore. |

**Stage**

| Status | Meaning |
|---|---|
| `new` | Not reached yet |
| `ready` | Can be run |
| `in process` | Running |
| `failed` | A step with error check failed |
| `finished` | All steps are finished |

**Step**: `new`, `in process`, `finished`, `failed`.

**Processing service job**: `queued`, `running`, `finished`, `failed`, `canceled` (see [processing service](processing-service.md)).


## Parallel branches

A stage with more than one `next_stages` starts parallel branches. All next stages become `ready` and can be run in any order, at the same time if the workflow sets `parallel_deployment_execution_allowed`.
While one of them is running, the deployment stays `in process`.

```
START ──► BUILD ──► TEST (UAT) ──► PROD ──► END
                       │
                       └─────────► ARCHIVE ──► END
```

Branches are merged by naming the same stage in the `next_stages` of several stages (`END` above). The merging stage becomes `ready`:

* as soon as one of the branches leading to it is finished, or
* only after the stages listed in its `after_stages_finished` are finished.

See [workflow configuration](workflow.md#parallel-branches).


## One deployment after the other

Unless the workflow sets `parallel_deployment_execution_allowed: true`:

* **Deployments of a project run in the order of their version.** A stage of version 42 can only be run when all older deployments of the project are `finished` or `canceled`.
  Cancel deployments you don't need anymore.
* **One stage at a time.** A stage can't be started while another stage of the same deployment is running.

Deployments of different projects are independent of each other.

For emergencies, define a separate hotfix workflow for the same project. It still has to wait for older open deployments of the project, so cancel or finish them first.


## Libraries and branches of a deployment

Each deployment has names which scripts can use (`meta_file.main_deploy_lib`, ...; in commands as [placeholders](workflow.md#placeholders)).
They are built from the internal id of the deployment (`42` → `000000042`):

| Name | Example | Used by the example scripts for |
|---|---|---|
| Main deployment library | `D000000042` | Save files of the objects |
| Backup library | `B000000042` | Backup of the replaced objects, the old tables of a DB deployment |
| Remote deployment library | `R000000042` | Save files on the target system |
| Release branch | `erp-42` (`{project}-{deploy_version}`, `C_GIT_BRANCH_RELEASE` in `etc/constants.py`) | Git branch of the release |


## Corrections

Buttons on the deployment page (and [Web API](webapi.md) endpoints) for situations which need a correction:

| Action | When | Effect |
|---|---|---|
| Reset stage | A stage stays `in process` although nothing runs anymore (e.g. the web app was restarted). Possible one minute after the last change of the stage, and not while it's in the processing service. | The stage is set to `ready`. Run it again with `Continue`. |
| Reset deployment status | The deployment stays `in process` although no stage runs | Its status follows from its stages again: `finished`, `failed` or `ready` |
| Reset last finished stage | A finished stage has to be run again, e.g. after a correction in the build | See [workflow configuration](workflow.md#reset-the-last-finished-stage) |
| Turn off error check of a step | A failed step can be ignored | The stage continues with the next step when it's run again |
| Cancel deployment | The deployment isn't needed anymore | Status `canceled`. Its stages are removed from the queue of the processing service. |


## Where the data is stored

| Data | Location |
|---|---|
| Deployments, stages, steps, objects, history, queue of the processing service | SQLite database `var/app.sqlite` |
| Logs of the steps and stage runs, generated files (save files, SQL, ...) | `meta/{project}/{date}/{version}/` |
| Configuration | `etc/`, `webapp/etc/` |
| API tokens (hashed) | `webapp/etc/keys.json` |
| Sessions of the web app | `webapp/sessions/` |
