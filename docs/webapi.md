# WebAPI requests

| Method | Url-Path |  Description |
| --- | -----| ----- |
| ```GET```\| ```POST```| ```/api/list_deployments/<project>```| JSON list of deployments
| ```POST``` | ```/api/generate_user_key```| Generates new key for logged in user |
| ```POST``` | ```/api/drop_key```| Drops key for logged in user | 
| ```POST``` | ```/api/run_stage```| Run the given stage | 
| ```POST``` | ```/api/get_meta_file_json```| The content of the given meta file will be returned | 
| ```POST``` | ```/api/get_action_log```| Returns the logs of the given action | 
| ```POST``` | ```/api/cancel_deployment```| Set deploymend to status ```canceled``` | 
| ```POST``` | ```api/create_deployment/<wf_name>/<commit>/<obj_list>```<br/>```api/create_deployment/<wf_name>/<commit>``` <br/> ```api/create_deployment/<wf_name>```| Creates new deployment based on the provided data | 
| ```POST``` | ```/api/set_check_error```| Turn ```on```\|```off``` error check for single processing steps |



## ```run_stage```

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


## ```get_meta_file_json```

```json
{
  "filename" : "{full meta file name}"
}
```

## ```get_action_log```

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


## ```set_check_error```
```json
{
  "stage_id" : "16",
  "filename" : "/home/prouzat1/i-releaser/meta/2024-07-10/1/deployment_1.json",
  "action_id" : 33,
  "checked" : false
}
```
