# WebAPI requests

## Overview

| Method | Url-Path |  Description |
| --- | -----| ----- |
| ```GET``` | ```/api/list_deployments/<project>```| JSON list of deployments
| ```POST``` | ```/api/generate_user_key```| Generates new key for logged in user |
| ```POST``` | ```/api/drop_key```| Drops key for logged in user | 
| ```POST``` | ```/api/run_stage```| Run the given stage | 
| ```POST``` | ```/api/get_meta_file_json```| The content of the given meta file will be returned | 
| ```POST``` | ```/api/get_action_log```| Returns the logs of the given action | 
| ```POST``` | ```/api/cancel_deployment```| Set deploymend to status ```canceled``` | 
| ```GET``` | ```api/create_deployment/<wf_name>/<commit>/<obj_list>```<br/>```api/create_deployment/<wf_name>/<commit>``` <br/> ```api/create_deployment/<wf_name>```| Creates new deployment based on the provided data | 
| ```POST``` | ```/api/set_check_error```| Turn ```on```\|```off``` error check for single processing steps |
| ```GET``` | ```/api/get_workflows```| Returns the content of `etc/workflow.json` file |


## Detailed description

### ```run_stage```

```json
{
  "stage_id": "{stage id}",
  "filename": "{meta-file-name}",
  "option": "continue|run_all"
}
```
#### Option
##### ```continue```
If last run of this stage failed, it will try to continue from the last failed step.

##### ```run_all```
The complete stage will be processed from the beginning


### ```get_meta_file_json```

```json
{
  "filename" : "{full meta file name}"
}
```

### ```get_action_log```

```json
{
  "stage_id" : "16",
  "filename" : "/home/prouzat1/i-releaser/meta/2024-07-10/1/deployment_1.json",
  "action_id" : 31,
  "history_element" : 0
}
```
##### ```history_element```
The entry number of the history list.


### ```set_check_error```
```json
{
  "stage_id" : "16",
  "filename" : "/home/prouzat1/i-releaser/meta/2024-07-10/1/deployment_1.json",
  "action_id" : 33,
  "checked" : false
}
```

### `create_deployment`

You can choose how much information you want to provide:

* workflow-name + commit hash + object list
* workflow-name + commit hash
* workflow-name

**Commit hash**  
When you provide the commit hash, it checks to see if another commit hash already exists.

**Object list**  
If given, i-Releaser will list these objects and the related deployment status.  
This list can also be created & imported during the deployment process. 

**Steps:**
1. Checks existing deployments (if commit hash is given)
2. Load workflow
3. Sets `START` stage
4. Generates a new deployment version
5. Set `release_branch` attribute based on the format `{project}-{deploy_version}`  
   This can be used to create new release branches based on this attribute.
6. Sets deployment library attributes (main, backup, remote deploy)
7. Import `object list` (if provided)
8. Set individual object actions which may needs to run on `START` stage
9. Write deployment meta file