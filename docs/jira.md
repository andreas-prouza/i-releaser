# Jira integration

i-Releaser reports the status of a deployment to the Jira issues of that deployment.

* **Jira Cloud**: Deployments appear in the development panel of the issue (`Deployments`),
  like the ones of Bitbucket, GitHub or Jenkins.
* **Jira Data Center**: Data Center has no deployments API for other tools.
  i-Releaser adds a link on the issue instead, which shows the current status, plus optional comments.

It uses workflow [hooks](workflow.md#hooks), so you can change it or write your own integration the same way.


## How it works

* You map stages of a workflow to Jira environments (e.g. stage `DEPLOY_PROD` → environment `Production`).
* The Jira issue keys are read from the custom data of the deployment (default `$.jira.ticket`).
* The state of each environment follows the status of its stage:

  | i-Releaser | Jira state |
  |---|---|
  | Deployment created or issue key added, stage not started yet | `pending` |
  | Stage is running | `in_progress` |
  | Stage finished | `successful` |
  | Stage failed | `failed` (becomes `in_progress` again when the stage is run again) |
  | Deployment canceled | `cancelled` for all environments which are not finished |

* Stages which are not mapped are ignored.
* Deployments without an issue key are not reported.
  If you add the key later (edit custom data), all mapped environments are reported with their current state.


## Setup

### 1. Script

Copy the example script (`setup3.13.sh` does this for new installations):

```sh
cp -n scripts/examples/jira.py scripts/
```

### 2. Jira credentials

**Jira Cloud**

1. In Jira as site admin: *Settings → Apps → OAuth credentials → Create credentials*
   ([Atlassian documentation](https://support.atlassian.com/jira-cloud-administration/docs/integrate-with-self-hosted-tools-using-oauth/))
2. Enter the URL of i-Releaser and select the permission **Deployments**.
3. Copy client ID and secret.

**Jira Data Center**

1. Create a personal access token for a technical user (*Profile → Personal Access Tokens*).
2. The user needs the permissions to link issues and (if you want comments) to add comments.

### 3. Configuration

Copy `etc/examples/jira.json` to `etc/jira.json` and adapt it.
Changes are loaded automatically.

```json
{
  "enabled": true,
  "mode": "cloud",
  "i_releaser_url": "https://ireleaser.example.com",
  "timeout_seconds": 10,
  "issue_key_paths": ["$.jira.ticket"],
  "cloud": {
    "site": "yourcompany.atlassian.net",
    "cloud_id": null,
    "client_id": "",
    "client_secret": null
  },
  "datacenter": {
    "base_url": "https://jira.example.com",
    "token": null,
    "remote_link": true,
    "comment_events": ["stage_finished", "stage_failed", "deployment_canceled"]
  },
  "workflows": {
    "simple_wf": {
      "environments": {
        "BUILD": { "id": "build", "display_name": "Build", "type": "development" },
        "DEPLOY_PROD": { "id": "prod", "display_name": "Production", "type": "production" }
      }
    }
  }
}
```

| Setting | Description |
|---|---|
| `mode` | `cloud` or `datacenter` |
| `i_releaser_url` | Base URL of i-Releaser. Jira links to the deployment page. |
| `timeout_seconds` | Max. time to wait for Jira. The stage waits for it. |
| `issue_key_paths` | JSONPaths in the custom data with the issue keys. A value may be a key (`ABC-1`), a comma separated list (`ABC-1, ABC-2`) or a json list. |
| `cloud.site` | Your Jira Cloud site. Used to get the `cloud_id` if it's not set. |
| `cloud.client_secret` | Or use env variable `I_RELEASER_JIRA_CLIENT_SECRET` (recommended) |
| `datacenter.token` | Or use env variable `I_RELEASER_JIRA_TOKEN` (recommended) |
| `datacenter.remote_link` | Add a link to the deployment on the issue. It's updated with each state change. |
| `datacenter.comment_events` | Add a comment to the issue for these [events](workflow.md#hooks) |
| `workflows.{name}.environments` | Mapping of stage name to Jira environment. `type` is one of `development`, `testing`, `staging`, `production`, `unmapped`. |

### 4. Workflow

Add the hooks to the workflow (`etc/workflows/*.json`) and make sure the issue key can be edited:

```json
"editable_fields": ["$.jira.ticket"],
"hooks": {
  "deployment_created": ["jira.on_event"],
  "custom_data_changed": ["jira.on_event"],
  "stage_started": ["jira.on_event"],
  "stage_finished": ["jira.on_event"],
  "stage_failed": ["jira.on_event"],
  "deployment_canceled": ["jira.on_event"]
}
```

Leave out events you don't want to report. E.g. without `deployment_created` Jira only shows an environment once its stage starts.

Hooks are stored with each deployment, so only new deployments are reported.


## Set the issue key

* When creating the deployment:
  ```
  POST /api/start_workflow/simple_wf
  {"custom_data": {"jira": {"ticket": "ABC-1"}}}
  ```
* Or in the web app: button `edit` next to `Custom data` on the deployment page.

> Note: Don't edit custom data while a stage is running. The running stage may overwrite the change when it saves the deployment.


## As a processing step

Instead of (or in addition to) hooks, you can report an environment as successful at a specific point of a stage:

```json
"step_action": [
  {"processing_step": "jira_successful", "environment": "SCRIPT", "execute": "jira.report_stage", "check_error": false}
]
```

With `"check_error": true` the stage fails if Jira can't be reached.


## Troubleshooting

* Errors are logged (`Hook jira.on_event for event ... failed`), but never stop a deployment.
* `Jira: unknown issue keys` / `deployment has been rejected`: The issue doesn't exist or the credentials have no access to that project.
* Nothing is reported: Check `enabled`, the workflow name in `workflows`, the stage names and the issue key in the custom data.
