# General

## Permissions

You can define `users` and `roles`.

Currently these permissions are available:

* `admin`
* `read`
* `start workflow`
* `deploy`
* `run`
* `change check error`
* `4-eyes check`
* `cancel workflow`

Permissions can be set on these level:
* `users`
* `roles`
  * `workflows`
    * `stages`


# Web

## Authentication

An IBM i is necessary

### HTTP authentication token

Each user can generate a http token.  
This token can be used for API calls.


# Individual scripts

You can add your own scripts into `scripts/` folder.

```python
def your_function(meta_file: Meta_File, stage_obj: Stage, action: Deploy_Action) -> None:
```