## Definition

* Workflow ID needs to be unique. Also over all projects
* Store workflows in separate json files



## Features

* Permission check
* 4 eyes check
* Parallel processing
  * Wait for next stage processing until a defined list of previous stages has been finished
  * Proceed processing, even not all previous stages has been finished



## General processing of stages

* Each stage may have defined one or multiple `next_stages` (only the stage name which needs to be unique)
* When a stage has been finished it's next stages will be loaded
* The new id of these stages will be set as list to the finished stage as `next_stage_ids`
* All specific actions to that stage are added
* If all stages has been finished, the deployment is set to status `finished`.


## Parallel workflows

Each step may have one or more `next_stages`.
You can merge them again to one single stept. Just define the same `next_stages` in the parallel steps.

The mergin step can start processing ...
* right after one of the parallel steps has been finished
* after one (or more) of the parallel steps has benn finished
  Just define which stages needs to get finished in the property list `after_stages_finished`


## Editable custom fields

A deployment may contain a custom json (`custom_data`).
A workflow defines which fields of that json can be edited by a user in the web app:

```json
"editable_fields": [
  "$.ticket",
  "$.approval.by",
  "$.tags[0]"
]
```

* Users need the permission `edit-custom-data` to edit these fields (button `edit` next to `Custom data` on the deployment page).
* Fields which do not exist yet in the custom data are created when they are saved.
* Only concrete paths are supported (no wildcards or filters):
  * `$.a.b` object keys
  * `$.a[0].b` list index (the index can't be larger than the current list size)
  * `$['my key']` quoted key
* Only paths listed in `editable_fields` can be changed. This is also checked by the server.
* The workflow definition is stored with each deployment. Deployments created before `editable_fields` was added to the workflow are not editable.
* A changed value keeps its type (number, boolean, json). New fields are stored as text.


## Hooks

A workflow can run python functions when something happens to a deployment.
E.g. to inform other systems like Jira (see [jira.md](jira.md)).

```json
"hooks": {
  "deployment_created": ["jira.on_event"],
  "stage_finished": ["jira.on_event", "my_script.notify"]
}
```

* Each entry has the format `filename.function_name` (without `.py`) of a file in the `scripts/` folder. Like a `SCRIPT` step.
* The function is called with:
  ```python
  def notify(event: str, meta_file: Meta_File, stage_obj: Stage|None) -> None:
  ```
  `stage_obj` is only set for stage events.
* Events:

  | Event | When |
  |---|---|
  | `deployment_created` | A new deployment has been created |
  | `deployment_finished` | All stages have been finished |
  | `deployment_canceled` | The deployment has been canceled |
  | `stage_started` | A stage starts to run (also when it's run again) |
  | `stage_finished` | All steps of a stage have been finished |
  | `stage_failed` | A step of a stage failed |
  | `custom_data_changed` | A user edited the custom data |

* Errors of a hook are logged only. They never stop or fail the deployment.
* Hooks run in the same thread as the stage (or the web request), so the stage waits for them. Keep them short and use timeouts for network calls.
* The workflow definition is stored with each deployment. Deployments created before `hooks` was added to the workflow don't run them.
