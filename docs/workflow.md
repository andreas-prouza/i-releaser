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
