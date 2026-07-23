#######################################################
# Load modules
#######################################################

# Configuration modules
import glob
import importlib
import sys, os

base_dir = os.path.realpath(os.path.dirname(__file__)+"/..")
#sys.path.insert(1, base_dir)
#os.chdir(base_dir)
sys.path.append(base_dir)

from etc import logger_config
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI


logging.debug(f"{sys.path=}")

# Custom modules
from routes import routes, initial
from modules.db import app_info_data, app_sqlite




@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager to handle startup and shutdown events.
    """
    # Initialize databases and tables
    app_sqlite.create_tables()
    app_info_data.add_app_info()
    
    yield
    # Add shutdown logic here if needed


#######################################################
# Set FastAPI configuration
#######################################################
app: FastAPI = initial.setup_fastapi(lifespan=lifespan)




#######################################################
# Dynamically load custom routes
#######################################################

custom_route_path = os.path.join(os.path.dirname(__file__), "custom", "routes")
if os.path.exists(custom_route_path):
    for path in glob.glob(f"{custom_route_path}/*.py"):
        module_name = os.path.basename(path)[:-3]
        if module_name != "__init__":
            try:
                importlib.import_module(f"custom.routes.{module_name}")
                logging.info(f"Successfully loaded custom route: {module_name}")
            except ImportError as e:
                logging.error(f"Failed to load custom route {module_name}: {e}")


#######################################################
# Set routes
#
#   Retrieve request data (POST & GET):
#     request.values.get('parameter')
#######################################################



app.add_api_route('/', routes.index, methods=['GET', 'POST'])

app.add_api_route('/api/list_deployments/{project}', routes.list_deployments, methods=['GET', 'POST'])


app.add_api_route('/project/{project}', routes.select_project, methods=['GET', 'POST'])


app.add_api_route('/log/{log}', routes.show_log, methods=['GET'])
app.add_api_route('/log/{log}/{number_of_lines}', routes.show_log, methods=['GET', 'POST'])


app.add_api_route('/api/start_workflow/{wf_name}', routes.start_workflow, methods=['GET'])
app.add_api_route('/api/start_workflow/{wf_name}', routes.start_workflow_post, methods=['POST'])

app.add_api_route('/login', routes.login, methods=['GET', 'POST'])

app.add_api_route('/user', routes.show_user, methods=['GET', 'POST'])

app.add_api_route('/api/generate_user_key', routes.generate_user_key, methods=['POST'])


app.add_api_route('/api/drop_key', routes.drop_user_key, methods=['POST'])




app.add_api_route('/logout', routes.logout, methods=['GET', 'POST'])



app.add_api_route('/workflows', routes.show_workflows, methods=['GET', 'POST'])

app.add_api_route('/settings', routes.show_settings, methods=['GET', 'POST'])


app.add_api_route('/show_details/{meta_file_id}', routes.show_details_by_id, methods=['GET', 'POST'])
app.add_api_route('/show_details/{project}/{version}', routes.show_details, methods=['GET', 'POST'])


app.add_api_route('/api/run_stage/{meta_file_id}/{stage_id}/{option}', routes.run_stage, methods=['GET'])


app.add_api_route('/api/get_meta_file_json/{meta_file_id}', routes.get_meta_file_json, methods=['POST'])



app.add_api_route('/api/get_activity_log/{id}', routes.get_activity_log, methods=['GET'])
app.add_api_route('/api/get_action_log/{id}', routes.get_action_log, methods=['GET'])

app.add_api_route('/api/show_processing_history/{meta_file_id}', routes.show_processing_history, methods=['GET'])


app.add_api_route('/api/cancel_deployment/{meta_file_id}', routes.cancel_deployment, methods=['GET'])

app.add_api_route('/api/reset_stage_status/{meta_file_id}/{stage_id}', routes.reset_stage_status, methods=['GET'])
app.add_api_route('/api/reset_deployment_status/{meta_file_id}', routes.reset_deployment_status, methods=['GET'])


app.add_api_route('/api/create_deployment/{wf_name}/{commit}/{obj_list}', routes.create_deployment, methods=['GET'])
app.add_api_route('/api/create_deployment/{wf_name}/{commit}', routes.create_deployment, methods=['GET'])
app.add_api_route('/api/create_deployment/{wf_name}', routes.create_deployment, methods=['GET'])
 


app.add_api_route('/api/set_check_error/{meta_file_id}/{stage_id}/{action_id}/{checked}', routes.set_check_error, methods=['GET'])


app.add_api_route('/api/set_source_ready_4_deployment/{meta_file_id}', routes.set_source_ready_4_deployment, methods=['POST'])


app.add_api_route('/api/get_stage_steps_html/{meta_file_id}/{stage_id}', routes.get_stage_steps_html, methods=['GET'])


app.add_api_route('/api/get_workflows', routes.get_workflows, methods=['GET'])


app.add_api_route('/api/get_projects', routes.get_projects, methods=['GET'])


########### Permissions

app.add_api_route('/api/add_permission', routes.add_permission, methods=['POST'])
app.add_api_route('/api/save_permissions', routes.save_permissions, methods=['POST'])




#######################################################
# Run service
#######################################################

if __name__ == '__main__':
    logging.info("Run WebApp from MAIN")
    os.environ["I_RELEASER_LOCAL_DEBUGGING"] = "True"
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)