import logging
from datetime import datetime, timedelta

from fastapi import Request
from modules import meta_file, stage_status, stages, deploy_action
from modules.job_status import Status as Job_Status
import base64
from web_modules import http_functions



div_container=f'\n<div id="flow_html_container" onClick="print_flow_connections()" class="flow_container">\n'
div_container_end=f'</div><!-- container end -->\n\n'

div_row=f'\n<div class="row row-cols-auto">\n'
div_row_end=f'</div><!-- row end -->\n'

div_column=f'\n<div class="col flow_step text-center">\n'
div_column_end=f'</div><!-- col end -->\n'

btn_class_list = {
  'None': 'btn-secondary',
  stage_status.Status.NEW.value: 'btn-info',
  stage_status.Status.READY.value: 'btn-primary',
  stage_status.Status.FAILED.value: 'btn-danger',
  stage_status.Status.FINISHED.value: 'btn-success',
  stage_status.Status.IN_PREPERATION.value: 'btn-dark',
  stage_status.Status.IN_PROCESS.value: 'btn-secondary',
  }


def get_stage_as_html_id(stage:str) -> str:
  """Generates an unique html id

  Args:
      stage (str): ID is a base64 code of the stage name.
                   This avoids special character problems

  Returns:
      str: html id
  """
  return f"flow_{base64.b64encode(stage.encode()).decode('ascii').replace('=', '')}"
  #return f"flow_{stage}"




def generate_stage_button(mf: meta_file.Meta_File, stage : stages.Stage):

  global btn_class_list

  btn_class = btn_class_list['None']
  btn_class=f' {btn_class_list.get(stage.get_dict().get("status", "None"),"None")}'
  return f'<button type="button" id="{get_stage_as_html_id(stage.name)}" onClick="flow_button_fokus=this.id" class="btn {btn_class}">{stage.name}</button>'



def generate_run_button(mf: meta_file.Meta_File, stage : stages.Stage):

  # Waiting for the processing service
  for job in mf.processing_jobs:
    if job.stage_id == stage.id and job.status == Job_Status.QUEUED:
      return f'<br/><button type="button" class="btn btn-sm btn-warning" title="Waiting for the processing service. Click to remove it from the queue." onclick="cancel_job({job.id})">queued</button>'

  # Like a deployment which is in process
  if len(mf.processing_jobs) > 0 and not mf.parallel_deployment_execution_allowed:
    return ''

  if mf.status not in [meta_file.Meta_file_status.FAILED, meta_file.Meta_file_status.READY] or stage.id not in mf.get_open_stages().get_all_ids():
    return ''
  if stage.status not in [stage_status.Status.FAILED, stage_status.Status.READY]:
    return ''

  global btn_class_list

  btn_class = btn_class_list['None']
  return f'<br/><img class="run" title="Run Stage" src="/static/assets/img/run-green.png" onclick="run_stage({mf.id}, {stage.id}, \'{stage.name}\')">'



def generate_reset_finished_button(mf: meta_file.Meta_File, stage : stages.Stage):

  # Only the last finished stage can be reset
  last_finished_stage = mf.get_last_finished_stage()
  if last_finished_stage is None or last_finished_stage.id != stage.id:
    return ''

  try:
    mf.check_reset_last_finished_stage()
  except Exception:
    return ''

  return f'<br/><img class="run" title="Reset status of the last finished stage" src="/static/assets/img/undo.png" onclick="reset_last_finished_stage({mf.id}, {stage.id}, \'{stage.name}\')">'



def generate_reset_button(mf: meta_file.Meta_File, stage : stages.Stage):

  if stage.status == stage_status.Status.FINISHED:
    return generate_reset_finished_button(mf, stage)

  if mf.status != meta_file.Meta_file_status.IN_PROCESS or stage.id not in mf.get_open_stages().get_all_ids():
    return ''
  if stage.status not in [stage_status.Status.IN_PREPERATION, stage_status.Status.IN_PROCESS, stage_status.Status.PREPARE]:
    return ''
  
  if stage.update_time > datetime.now() - timedelta(seconds=meta_file.STAGE_RESET_WAIT_SECONDS):
    return ''

  global btn_class_list

  btn_class = btn_class_list['None']
  return f'<br/><img class="run" title="Reset Stage" src="/static/assets/img/undo.png" onclick="reset_stage_status({mf.id}, {stage.id})">'



def generate_action_button(action : deploy_action.Deploy_Action):

  global btn_class_list
  
  btn_class = btn_class_list['None']
  btn_class=f' {btn_class_list.get(action.get_dict().get("status", "None"),"None")}'
  return f'<button class="btn btn-sm {btn_class}">{action.status.value}</button>'


def generate_stage_steps_html(request: Request, mf: meta_file.Meta_File, stage : stages.Stage):

  logging.debug(f"Generate HTML for stage {stage.name} ({stage.id})")

  actions = stage.actions.get_actions_as_dict()

  # Add subactions to root list
  for a in actions:
    if len(a['sub_actions']) == 0:
      continue
    i=0
    for sa in a['sub_actions']:
      i+=1
      sa['sequence'] = f"{a['sequence']}.{i}"
  
  actions.sort(key=lambda x: x['sequence'])
  #---------------------------------------------

  multi='s'
  if len(actions) == 1:
    multi=''

  if len(actions) == 0:
    logging.warning('No actions found')
    return ''

  html_actions = http_functions.get_html_response(request, 'overview/details/stage-actions-details.html', 
                                    meta_file_id=mf.id,
                                    stage=stage.get_dict(), 
                                    cmds=actions, 
                                    run_stage_button=generate_run_button(mf=mf, stage=stage),
                                    reset_stage_button=generate_reset_button(mf=mf, stage=stage)
                                  ).body.decode()
  #html_actions = render_template('overview/details/quotes.html', html=html_actions)
  
  html_actions=html_actions.replace('\n', '')
  html_actions=html_actions.replace('\r\n', '')
  html_actions=html_actions.replace('&quot;', '\\&quot;')
  html_actions=html_actions.replace('&#39;', '\\&#39;')

  return html_actions



def generate_steps(request: Request, mf: meta_file.Meta_File, stage : stages.Stage):

  html = http_functions.get_html_response(request, 'overview/details/stage-actions.html', 
                                          meta_file_id=mf.id,
                                          stage_id=stage.id, 
                                          stage_name=stage.name).body.decode()

  return html



def get_flow_stage(request: Request, mf: meta_file.Meta_File, stage : stages.Stage, flow_stages: list, flow_connection: list) -> str:
  """Generates the flow diagram of stages

  Args:
      mf (meta_file.Meta_File): Meta file object
      stage (stages.Stage): Stage object
      flow_stages (list): Gets the html ids of the stages
      flow_connection (list): Gets the connections between the stages

  Returns:
      str: html code
  """

  flow_stages.append(get_stage_as_html_id(stage.name))

  next_stages = mf.get_next_stages(stage)
  sub_row=''

  i=0
  for ns in next_stages:
    i+=1

    direction_from='right'
    if i>1:
      direction_from='bottom'
    flow_connection.append({'from': f"{get_stage_as_html_id(stage.name)}", 'to': f"{get_stage_as_html_id(ns.name)}", 'direction_from': direction_from, 'direction_to': 'left'})
    
    # Every stage will only be printed once
    if f"{get_stage_as_html_id(ns.name)}" in flow_stages:
      continue
    
    # All next stages in a new Row
    sub_row+=div_row
    sub_row+=get_flow_stage(request, mf, ns, flow_stages, flow_connection)
    sub_row+=div_row_end

  # This stage
  html=div_column
  html+= generate_stage_button(mf, stage)
  html+= generate_run_button(mf, stage)
  html+= generate_reset_button(mf, stage)

  if len(stage.processing_steps) > 0:
    html+= generate_steps(request, mf, stage)
  html+=div_column_end
  # Next stages
  html+=div_column
  html+=sub_row
  html+=div_column_end

  return html



def get_flowchar_html(request: Request, mf: meta_file.Meta_File):

  flow_connection=[]
  flow_stages=[]
  #mf.workflow.load_workflow_data()


  html=div_container
  html+=div_row
  html+=get_flow_stage(request, mf, mf.get_stages_by_name('START')[0], flow_stages, flow_connection)
  html+=div_row_end
  html+=div_container_end
  
  java_script=''
  for fs in flow_stages:
    java_script+=f'\n  let {fs} = document.getElementById("{fs}");'

  for fc in flow_connection:
    java_script+=f'\n  connectItems({fc["from"]}, {fc["to"]}, "{fc["direction_from"]}", "{fc["direction_to"]}");'

  return {'html': html, 'java_script': java_script}
