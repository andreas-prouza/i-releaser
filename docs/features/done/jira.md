# Jira integration

## Current situation

It's possible to define workflows where the JIRA ticket-id can be stored in costom data.
```json
{
  "name": "simple_wf",
  "default_project": "test",
  "parallel_deployment_execution_allowed": true,
  "editable_fields": ["$.jira.ticket", "$.approval.by"],
  "step_action": [
    {
      "processing_step": "print_pwd",
      "environment": "PASE",
      "execute": "pwd",
      "check_error": true
    }
  ],
  "stages" : [
    {
      "name": "START",
      "next_stages": ["BUILD"],
      "host": "localhost",
      "processing_steps": ["pre", "print_pwd", "post"],
      "clear_files": true
    },
    {
      "name": "BUILD",
      "next_stages": ["END"],
      "host": "localhost",
      "processing_steps": ["pre", "print_pwd", "load_object_list"],
      "clear_files": true
    },
    {
      "name": "END",
      "description": "Finished"
    }
  ]
}
```

## Target
* In JIRA developer section, I also want to see all deployments with it's status (`started/new` at the beginning)
* If a deployment pass a specific stage, JIRA should get informed that the deployment was perfomed successfully
* Maybe this can be handled by a user defined python script in a stage?
  So the concept is still open and the user can do it by itself.
## Solution

* Generic workflow [hooks](../../workflow.md#hooks): python functions from `scripts/` which run on
  `deployment_created`, `deployment_finished`, `deployment_canceled`, `stage_started`, `stage_finished`, `stage_failed`, `custom_data_changed`.
  A script step alone can't report creation, failed steps (the stage stops before) or cancel.
* Jira client (`modules/jira_client.py`) with example hook script `scripts/examples/jira.py`
  * Jira Cloud: Deployments API (development panel of the issue), OAuth client credentials
  * Jira Data Center: No deployments API for other tools. Remote link with the current state and optional comments instead.
* Stages are mapped to Jira environments in `etc/jira.json`. The Jira state follows the stage status (`pending`, `in_progress`, `successful`, `failed`, `cancelled`).
* Documentation: [jira.md](../../jira.md)

## Definition of done
* A deployment with an issue key in custom data is shown as `pending` in Jira right after it's created (or the key is added)
* Mapped stages report `in_progress`, `successful` and `failed`
* Canceled deployments report `cancelled`
* Errors in Jira never stop a deployment
