"""
Web API v2 (docs/features/api-v2.md): resources under /api/v2/, each the use case of modules/application.

* Answers: the resource itself; lists `{"items": [...], "next_cursor": "..."}` (null on the last page).
  Errors: `{"status": "error", "message": "..."}` (WebMiddleware and the exception handlers of routes/initial.py).
* Only these paths are in the OpenAPI description (/docs and /openapi.json).
* Handlers are plain functions: they run in a thread of FastAPI (the use cases block).
"""
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field, StrictBool, conlist

from modules import current_user, errors, permission_config, permissions
from modules.application import deployments
from modules.db import api_token_data

from web_modules import app_login, audit, http_functions, two_factor


# Documents the token in OpenAPI. auto_error=False: the session of the web app works as well
bearer = HTTPBearer(auto_error=False, description="API token of the page 'My account'")

router = APIRouter(prefix='/api/v2', dependencies=[Depends(bearer)])

DEPLOYMENTS = 'Deployments'
STAGES = 'Stages and steps'
JOBS = 'Processing service'
TOKENS = 'API tokens'



#---------------------------------------------------------
# Bodies (pydantic 1: FastAPI 0.125 with pydantic 1, see docs/technik.md#fastapi-and-pydantic)
#---------------------------------------------------------

class Strict(BaseModel):
    class Config:
        # A typo of a field is an error, not ignored
        extra = 'forbid'


class Deployment_Create(Strict):
    workflow: str = Field(..., description="Name of the workflow")
    commit: str|None = Field(None, description="Only one deployment of a project which isn't canceled can have a commit")
    custom_data: dict[str, Any] = Field(default_factory=dict, description="Any JSON, limited by `create_fields` of the workflow")
    compiles: list[Any]|None = Field(None, description="Compile list (`compiles` of an OBI build list)")
    object_list: str|None = Field(None, description="Path of a file with the objects (docs/workflow.md#object-list)")


class Run_Create(Strict):
    mode: Literal['continue', 'all'] = Field('continue', description="`continue`: the steps which haven't finished; `all`: all steps")
    step: str|None = Field(None, description="Only this processing step")
    run_at: str|None = Field(None, description="Scheduled run (ISO 8601 with time zone), processing mode `service` only")


class Stage_Reset(Strict):
    kind: Literal['hanging', 'last-finished'] = Field(..., description="`hanging`: a stage which hangs in process; `last-finished`: the stage which has finished last")


class Custom_Data_Change(Strict):
    fields: dict[str, Any] = Field(..., description="JSONPath -> new value, only the `editable_fields` of the workflow")


class Object_Ref(Strict):
    lib: str
    name: str
    type: str


class Objects_Change(Strict):
    objects: conlist(Object_Ref, min_items=1)
    # Strict: pydantic 1 would read "no" as false
    ready: StrictBool


class Step_Change(Strict):
    check_error: StrictBool = Field(..., description="A failure of the step stops the stage")


class Token_Create(Strict):
    name: str = Field(..., description="To recognize it, e.g. the client which uses it", max_length=app_login.MAX_TOKEN_NAME_LENGTH)
    scope: Literal['read', 'write'] = Field('write', description="`read`: only GET requests")
    expires_in_days: int|None = Field(None, description="Default and maximum: C_TOKEN_MAX_DAYS of the installation")


class Deployment_Item(BaseModel):
    id: int
    project: str
    version: int
    workflow: str|None
    status: str
    commit: str|None
    create_time: str|None
    update_time: str|None


class Deployment_Page(BaseModel):
    items: list[Deployment_Item]
    next_cursor: str|None



def page(items: list, next_cursor: str|None=None):
    return http_functions.get_json_response({'items': items, 'next_cursor': next_cursor})



def deployment(meta_file_id: int, status: int=200):
    """The deployment as it is now"""
    return http_functions.get_json_response(deployments.load(meta_file_id).get_all_data_as_dict(), status=status)



#---------------------------------------------------------
# Projects and workflows
#---------------------------------------------------------

@router.get('/projects', tags=[DEPLOYMENTS], summary="Projects with the number of their deployments per status")
def get_projects(request: Request):

    from routes import routes
    counts = routes.get_project_counts()
    return page([{'name': name, 'deployments': statuses} for name, statuses in counts.items()])



@router.get('/workflows', tags=[DEPLOYMENTS], summary="Workflows the user may read")
def get_workflows(request: Request):

    from routes import routes
    return page(routes.get_readable_workflows())



#---------------------------------------------------------
# Deployments
#---------------------------------------------------------

@router.get('/deployments', tags=[DEPLOYMENTS], response_model=Deployment_Page, summary="Deployments, newest first")
def list_deployments(request: Request, project: str|None=None, status: str|None=None,
                     limit: int=Query(deployments.DEFAULT_LIMIT, description=f"1 to {deployments.MAX_LIMIT}"),
                     cursor: str|None=Query(None, description="`next_cursor` of the page before")):

    items, next_cursor = deployments.list_deployments(project=project, status=status, limit=limit, cursor=cursor)
    return page(items, next_cursor)



@router.post('/deployments', tags=[DEPLOYMENTS], status_code=201, summary="Create a deployment")
def create_deployment(request: Request, body: Deployment_Create):

    mf = deployments.create_deployment(body.workflow, custom_data=body.custom_data, compiles=body.compiles, commit=body.commit, object_list=body.object_list)
    return deployment(mf.id, status=201)



@router.get('/deployments/{meta_file_id}', tags=[DEPLOYMENTS], summary="A deployment with its stages, steps and objects")
def get_deployment(request: Request, meta_file_id: int):
    return http_functions.get_json_response(deployments.get_deployment(meta_file_id).get_all_data_as_dict())



@router.post('/deployments/{meta_file_id}/cancel', tags=[DEPLOYMENTS], summary="Cancel a deployment (a running stage isn't stopped)")
def cancel_deployment(request: Request, meta_file_id: int):

    deployments.cancel_deployment(meta_file_id)
    return deployment(meta_file_id)



@router.post('/deployments/{meta_file_id}/reset', tags=[DEPLOYMENTS], summary="A deployment which hangs in process: its status follows from its stages")
def reset_deployment(request: Request, meta_file_id: int):

    deployments.reset_deployment(meta_file_id)
    return deployment(meta_file_id)



@router.patch('/deployments/{meta_file_id}/custom-data', tags=[DEPLOYMENTS], summary="Change editable fields of the custom data")
def edit_custom_data(request: Request, meta_file_id: int, body: Custom_Data_Change):

    changed = deployments.edit_custom_data(meta_file_id, body.fields)
    return http_functions.get_json_response({'changed': changed, 'custom_data': deployments.load(meta_file_id).custom_data})



@router.patch('/deployments/{meta_file_id}/objects', tags=[DEPLOYMENTS], summary="Include (ready) or exclude objects")
def set_objects_ready(request: Request, meta_file_id: int, body: Objects_Change):

    result = deployments.set_objects_ready(meta_file_id, [o.dict() for o in body.objects], body.ready)
    return http_functions.get_json_response(result)



@router.get('/deployments/{meta_file_id}/history', tags=[DEPLOYMENTS], summary="Who did what when, oldest first")
def get_history(request: Request, meta_file_id: int):
    return page(deployments.get_history(meta_file_id))



@router.get('/deployments/{meta_file_id}/jobs', tags=[JOBS], summary="Runs of the stages by the processing service")
def get_jobs(request: Request, meta_file_id: int):
    return page(deployments.get_jobs(meta_file_id))



#---------------------------------------------------------
# Stages and steps
#---------------------------------------------------------

@router.post('/deployments/{meta_file_id}/stages/{stage_id}/runs', tags=[STAGES], status_code=202,
             summary="Run a stage in the background, or schedule it (run_at)")
def run_stage(request: Request, meta_file_id: int, stage_id: int, body: Run_Create|None=None):

    body = body or Run_Create()
    result = deployments.run_stage(meta_file_id, stage_id, mode=body.mode, run_at=body.run_at, processing_step=body.step)
    return http_functions.get_json_response(result, status=202)



@router.post('/deployments/{meta_file_id}/stages/{stage_id}/reset', tags=[STAGES], summary="Set a stage back to ready")
def reset_stage(request: Request, meta_file_id: int, stage_id: int, body: Stage_Reset):

    stage = deployments.reset_stage(meta_file_id, stage_id, body.kind)
    return http_functions.get_json_response({'id': stage.id, 'name': stage.name, 'status': stage.status.value})



@router.post('/deployments/{meta_file_id}/stages/{stage_id}/approvals', tags=[STAGES], status_code=201,
             summary="Approve a stage with the four-eyes check")
def approve_stage(request: Request, meta_file_id: int, stage_id: int):

    approval = deployments.approve_stage(meta_file_id, stage_id, confirm=lambda: two_factor.require_recent_code(request))
    return http_functions.get_json_response({'approved_by': approval['user'], 'time': approval['time']}, status=201)



@router.patch('/deployments/{meta_file_id}/steps/{step_id}', tags=[STAGES], summary="Whether a failure of the step stops the stage")
def change_step(request: Request, meta_file_id: int, step_id: int, body: Step_Change):

    stage, _ = deployments.find_step(deployments.get_deployment(meta_file_id), step_id)
    deployments.set_check_error(meta_file_id, stage.id, step_id, body.check_error)

    return http_functions.get_json_response({'id': step_id, 'check_error': body.check_error})



@router.get('/deployments/{meta_file_id}/steps/{step_id}/log', tags=[STAGES], summary="The runs of a step with their output")
def get_step_log(request: Request, meta_file_id: int, step_id: int):
    return page(deployments.get_step_log(meta_file_id, step_id))



#---------------------------------------------------------
# Processing service
#---------------------------------------------------------

@router.delete('/jobs/{job_id}', tags=[JOBS], status_code=204, summary="Remove a run from the queue (before it has started)")
def cancel_job(request: Request, job_id: int):

    deployments.cancel_job(job_id)
    return Response(status_code=204)



#---------------------------------------------------------
# API tokens: only in the web app (with the session), not with a token: a stolen token can't create others
#---------------------------------------------------------

def token_view(token: dict) -> dict:
    return {key: token[key] for key in ['id', 'name', 'scope', 'masked', 'created_at', 'expires_at', 'last_used_at', 'legacy']}



@router.get('/tokens', tags=[TOKENS], summary="The own API tokens (web app only)")
def list_tokens(request: Request):

    two_factor.require_session(request)
    return page([token_view(token) for token in api_token_data.get_of_user(current_user.get_user())])



@router.post('/tokens', tags=[TOKENS], status_code=201, summary="Create an API token (web app only). The token is in the answer once.")
def create_token(request: Request, body: Token_Create):

    two_factor.require_recent_code(request)

    token, row = app_login.create_token(current_user.get_user(), body.name, body.scope, body.expires_in_days)
    audit.record(request, 'token_created', details={'name': row['name'], 'scope': row['scope']})

    return http_functions.get_json_response({**token_view(row), 'token': token}, status=201)



@router.delete('/tokens/{token_id}', tags=[TOKENS], status_code=204, summary="Delete an own token; admins: the token of any user (web app only)")
def delete_token(request: Request, token_id: int):

    two_factor.require_session(request)
    token = api_token_data.get(token_id)
    user = (current_user.get_user() or '').lower()

    if token is not None and token['user'] != user:
        # Another user's token: only an admin may see that it exists
        if not permission_config.is_user_allowed(user, permissions.PermissionAction.ADMIN):
            token = None
        else:
            two_factor.require_recent_code(request)

    if token is None:
        raise errors.Not_Found_Error(f"Token {token_id} not found")

    api_token_data.delete(token_id)

    if token['user'] == user:
        audit.record(request, 'token_deleted', details={'name': token['name']})
    else:
        logging.warning(f"API token '{token['name']}' of user {token['user']} revoked by {user}")
        audit.record(request, 'token_revoked', object=token['user'], details={'name': token['name']})

    return Response(status_code=204)
