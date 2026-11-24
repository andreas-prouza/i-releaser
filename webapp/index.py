#######################################################
# Load modules
#######################################################

# Configuration modules
import asyncio
import glob
import importlib
import platform
import sys, os

base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
#sys.path.insert(1, base_dir)
#os.chdir(base_dir)
sys.path.append(base_dir)

# Configures the log (an import for its side effect)
from etc import logger_config  # noqa: F401
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.routing import APIRoute


logging.debug(f"{sys.path=}")

# Custom modules
from routes import api_v2, routes, initial
from web_modules import admin_view
from modules import settings_check
from modules.db import audit_data, notification_data
from modules import notifications, retention
from etc import constants
from modules import processing_settings
from modules.db import app_info_data, app_sqlite
from web_modules import app_login, server_sessions

# Seconds between two deletions of expired sessions
SESSION_CLEANUP_INTERVAL_SECONDS = 3600



async def watch_processing_service() -> None:
    """Auto start of the processing service: at the start of the web app and every C_SERVICE_WATCHDOG_INTERVAL seconds"""

    while True:
        try:
            # In a thread: the start of the service takes some seconds
            await asyncio.to_thread(processing_settings.ensure_service_running)
        except Exception as e:
            logging.exception(e, stack_info=True)

        await asyncio.sleep(constants.C_SERVICE_WATCHDOG_INTERVAL)




async def delete_expired_sessions() -> None:

    while True:
        try:
            await asyncio.to_thread(server_sessions.delete_expired_sessions)
            # Retention of the audit log (docs/features/audit-log.md) and of old deployments, once a day (docs/features/data-retention.md)
            await asyncio.to_thread(audit_data.remove_older_than, constants.C_AUDIT_RETENTION_DAYS)
            await asyncio.to_thread(retention.run_if_due)
            await asyncio.to_thread(notification_data.remove_older_than, notifications.KEEP_DAYS)
        except Exception as e:
            logging.exception(e, stack_info=True)

        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)



@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager to handle startup and shutdown events.
    """
    if app_login.is_local_debugging():

        # gunicorn is how the web app runs on a server, and i-Releaser runs on IBM i (docs/bugfixes/minor-web-defects-2026-11.md, item 12)
        if 'gunicorn' in sys.modules or platform.system() == 'OS400':
            raise RuntimeError("I_RELEASER_LOCAL_DEBUGGING turns off the password check. It must not be set on a server!")

        logging.warning("I_RELEASER_LOCAL_DEBUGGING is set: the password check of the login is turned off!")

    # An invalid setting stops the start with a message (docs/features/core-redesign.md, step 7)
    settings_check.check_at_start()
    app_login.check_login_settings()

    if constants.C_CSP_REPORT_ONLY:
        logging.warning("C_CSP_REPORT_ONLY is set: the Content-Security-Policy is only reported, not enforced. Move your custom templates to script files and remove it.")

    # Initialize databases and tables
    app_sqlite.create_tables()
    app_sqlite.check_updates()
    app_info_data.add_app_info()

    # The tokens of webapp/etc/keys.json move into the database (docs/features/api-v2.md#tokens)
    app_login.migrate_keys_file()

    processing_settings.take_over_old_settings_file()

    # Sends the notifications of all processes, also those which a job process couldn't send (docs/features/notifications.md)
    notifications.load_config()
    notifications.start_sender()

    cleanup_task = asyncio.create_task(delete_expired_sessions())
    # After the update of the database: the service doesn't start with an older one
    watchdog_task = asyncio.create_task(watch_processing_service())

    yield

    cleanup_task.cancel()
    watchdog_task.cancel()


#######################################################
# Set FastAPI configuration
#######################################################
app: FastAPI = initial.setup_fastapi(lifespan=lifespan)




#######################################################
# Set routes
#
#   Retrieve request data (POST & GET):
#     request.values.get('parameter')
#######################################################



app.add_api_route('/', routes.index, methods=['GET', 'POST'])

app.add_api_route('/list-objects', routes.list_objects, methods=['GET', 'POST'])

app.add_api_route('/api/deploy_object_lifecycle/{project}/{prod_lib}/{name}/{type}/{attribute}', routes.deploy_object_lifecycle, methods=['GET'])
app.add_api_route('/api/deploy_objects', routes.get_deploy_objects, methods=['GET'])
app.add_api_route('/list-objects/history', routes.object_history, methods=['GET'])

app.add_api_route('/api/list_deployments/{project}', routes.list_deployments, methods=['GET', 'POST'])


app.add_api_route('/project/{project}', routes.select_project, methods=['GET', 'POST'])


app.add_api_route('/log/{log}', routes.show_log, methods=['GET'])
app.add_api_route('/log/{log}/download', routes.download_log, methods=['GET'])
app.add_api_route('/log/{log}/{number_of_lines}', routes.show_log, methods=['GET', 'POST'])


app.add_api_route('/api/start_workflow/{wf_name}', routes.start_workflow, methods=['GET'])
app.add_api_route('/api/start_workflow/{wf_name}', routes.start_workflow_post, methods=['POST'])

app.add_api_route('/login', routes.login, methods=['GET', 'POST'])

app.add_api_route('/user', routes.show_user, methods=['GET', 'POST'])

app.add_api_route('/api/generate_user_key', routes.generate_user_key, methods=['POST'])


app.add_api_route('/api/drop_key', routes.drop_user_key, methods=['POST'])
app.add_api_route('/api/unblock_login/{user}', routes.unblock_login, methods=['POST'])
app.add_api_route('/api/revoke_token/{user}', routes.revoke_token, methods=['POST'])
app.add_api_route('/healthz', routes.healthz, methods=['GET'], include_in_schema=False)
app.add_api_route('/api/retention/run', routes.run_retention, methods=['POST'])
app.add_api_route('/api/notifications/test/{channel}', routes.send_test_notification, methods=['POST'])
app.add_api_route('/api/approve_stage/{meta_file_id}/{stage_id}', routes.approve_stage, methods=['POST'])
app.add_api_route('/api/mfa/setup', routes.mfa_setup, methods=['POST'])
app.add_api_route('/api/mfa/enable', routes.mfa_enable, methods=['POST'])
app.add_api_route('/api/mfa/disable', routes.mfa_disable, methods=['POST'])
app.add_api_route('/api/mfa/recovery_codes', routes.mfa_recovery_codes, methods=['POST'])
app.add_api_route('/api/mfa/verify', routes.mfa_verify, methods=['POST'])
app.add_api_route('/api/mfa/reset/{user}', routes.mfa_reset, methods=['POST'])




app.add_api_route('/logout', routes.logout, methods=['GET', 'POST'])



app.add_api_route('/workflows', routes.show_workflows, methods=['GET', 'POST'])

app.add_api_route('/settings', routes.show_settings, methods=['GET', 'POST'])
app.add_api_route('/settings/permissions', routes.show_permissions, methods=['GET'])
app.add_api_route('/settings/processing', routes.show_processing, methods=['GET'])
app.add_api_route('/settings/audit', routes.show_audit, methods=['GET'])
app.add_api_route('/settings/audit.csv', routes.download_audit, methods=['GET'])


app.add_api_route('/show_details/{meta_file_id}', routes.show_details_by_id, methods=['GET', 'POST'])
app.add_api_route('/show_details/{project}/{version}', routes.show_details, methods=['GET', 'POST'])
app.add_api_route('/show_details/{meta_file_id}/stage/{stage_id}', routes.show_stage_steps, methods=['GET'])


app.add_api_route('/api/run_stage/{meta_file_id}/{stage_id}/{option}', routes.run_stage, methods=['GET', 'POST'])


app.add_api_route('/api/get_meta_file_json/{meta_file_id}', routes.get_meta_file_json, methods=['POST'])



app.add_api_route('/api/get_activity_log/{id}', routes.get_activity_log, methods=['GET'])
app.add_api_route('/api/get_action_log/{id}', routes.get_action_log, methods=['GET'])

app.add_api_route('/api/show_processing_history/{meta_file_id}', routes.show_processing_history, methods=['GET'])


app.add_api_route('/api/cancel_deployment/{meta_file_id}', routes.cancel_deployment, methods=['GET', 'POST'])
app.add_api_route('/api/cancel_job/{job_id}', routes.cancel_job, methods=['GET', 'POST'])
app.add_api_route('/api/set_processing_mode/{mode}', routes.set_processing_mode, methods=['POST'])
app.add_api_route('/api/processing_service/{action}', routes.control_processing_service, methods=['POST'])
app.add_api_route('/api/set_service_auto_start/{enabled}', routes.set_service_auto_start, methods=['POST'])
app.add_api_route('/api/edit_custom_data/{meta_file_id}', routes.edit_custom_data, methods=['POST'])

app.add_api_route('/api/reset_stage_status/{meta_file_id}/{stage_id}', routes.reset_stage_status, methods=['GET', 'POST'])
app.add_api_route('/api/reset_last_finished_stage/{meta_file_id}/{stage_id}', routes.reset_last_finished_stage, methods=['GET', 'POST'])
app.add_api_route('/api/reset_deployment_status/{meta_file_id}', routes.reset_deployment_status, methods=['GET', 'POST'])


app.add_api_route('/api/create_deployment/{wf_name}/{commit}/{obj_list}', routes.create_deployment, methods=['GET', 'POST'])
app.add_api_route('/api/create_deployment/{wf_name}/{commit}', routes.create_deployment, methods=['GET', 'POST'])
app.add_api_route('/api/create_deployment/{wf_name}', routes.create_deployment, methods=['GET', 'POST'])
 


app.add_api_route('/api/set_check_error/{meta_file_id}/{stage_id}/{action_id}/{checked}', routes.set_check_error, methods=['GET', 'POST'])


app.add_api_route('/api/set_source_ready_4_deployment/{meta_file_id}', routes.set_source_ready_4_deployment, methods=['POST'])
app.add_api_route('/api/set_objects_ready/{meta_file_id}', routes.set_objects_ready, methods=['POST'])


app.add_api_route('/api/get_stage_steps_html/{meta_file_id}/{stage_id}', routes.get_stage_steps_html, methods=['GET'])
app.add_api_route('/api/deployment_objects/{meta_file_id}', routes.get_deployment_objects, methods=['GET'])
app.add_api_route('/api/watch_state/{meta_file_id}', routes.watch_state, methods=['GET'])


app.add_api_route('/api/get_workflows', routes.get_workflows, methods=['GET'])


app.add_api_route('/api/get_projects', routes.get_projects, methods=['GET'])


########### Permissions

app.add_api_route('/api/add_permission', routes.add_permission, methods=['POST'])
app.add_api_route('/api/save_permissions', routes.save_permissions, methods=['POST'])
app.add_api_route('/api/permissions', routes.get_permissions, methods=['GET'])

########### Web API v2 (docs/features/api-v2.md)

app.include_router(api_v2.router)




#######################################################
# Dynamically load custom routes
#
#   After the routes of the web app: a custom route can't replace one of them
#   (docs/bugfixes/minor-web-defects-2026-11.md, item 6)
#######################################################

def get_route_keys() -> set[tuple[str, str]]:
    return {(route.path, method) for route in app.routes for method in (getattr(route, 'methods', None) or [])}


def load_custom_routes() -> None:

    custom_route_path = os.path.join(os.path.dirname(__file__), "custom", "routes")
    if not os.path.exists(custom_route_path):
        return

    core_routes = get_route_keys()

    for path in sorted(glob.glob(f"{custom_route_path}/*.py")):
        module_name = os.path.basename(path)[:-3]
        if module_name == "__init__":
            continue

        before = len(app.routes)
        try:
            importlib.import_module(f"custom.routes.{module_name}")
        except Exception as e:
            # The web app starts without it
            logging.exception(f"Failed to load custom route {module_name}: {e}")
            admin_view.CUSTOM_ROUTE_ERRORS[module_name] = f"{type(e).__name__}: {e}"
            continue

        added = {(route.path, method) for route in app.routes[before:] for method in (getattr(route, 'methods', None) or [])}
        conflicts = sorted(added & core_routes)
        if conflicts:
            raise RuntimeError(f"Custom route file {module_name}.py uses paths of the web app: {', '.join(f'{m} {p}' for p, m in conflicts)}. Rename them.")

        logging.info(f"Successfully loaded custom route: {module_name}")



load_custom_routes()

# The OpenAPI description (/docs) shows only the Web API v2 (docs/features/api-v2.md): not the pages, not v1, not custom routes
for route in app.routes:
    if isinstance(route, APIRoute) and not route.path.startswith('/api/v2/'):
        route.include_in_schema = False



#######################################################
# Run service
#######################################################

if __name__ == '__main__':
    logging.info("Run WebApp from MAIN")
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)