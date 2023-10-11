from __future__ import annotations
import logging
from modules import meta_file, stages, deploy_action
from modules.cmd_status import Status as Cmd_Status
from flask import render_template
import base64


div_container=f'\n<div id="flow_html_container" onClick="print_flow_connections()" class="flow_container">\n'
div_container_end=f'</div><!-- container end -->\n\n'

div_row=f'\n<div class="row row-cols-auto">\n'
div_row_end=f'</div><!-- row end -->\n'

div_column=f'\n<div class="col flow_step text-center">\n'
div_column_end=f'</div><!-- col end -->\n'

btn_class_list = {
  'None': 'btn-secondary',
  Cmd_Status.NEW.value: 'btn-info',
  Cmd_Status.FAILED.value: 'btn-danger',
  Cmd_Status.FINISHED.value: 'btn-success',
  Cmd_Status.IN_PREPERATION.value: 'btn-dark',
  }

flow_stages=[]
flow_connection=[]



def get_stage_as_html_id(stage:str) -> str:
  return f"flow_{base64.b64encode(stage.encode()).decode('ascii').replace('=', '')}"




def generate_stage_button(mf: meta_file.Meta_File, stage : stages.Stage):

  global btn_class_list

  btn_class = btn_class_list['None']
  logging.debug(f"{stage.name}: {stage.get_dict().get('status')=}")
  btn_class=f' {btn_class_list.get(stage.get_dict().get("status", "None"),"None")}'
  return f'<button type="button" id="{get_stage_as_html_id(stage.name)}" onClick="flow_button_fokus=this.id" class="btn {btn_class}">{stage.name}</button>'



def generate_run_button(mf: meta_file.Meta_File, stage : stages.Stage):

  global btn_class_list

  btn_class = btn_class_list['None']
  logging.debug(f"{stage=}")
  return f'<br/><img class="run" src="/static/assets/img/run-green.png" onclick="runStage(\'{mf.file_name}\', \'{stage.name}\')">'



def generate_action_button(action : deploy_action.Deploy_Action):

  global btn_class_list
  
  btn_class = btn_class_list['None']
  logging.debug(f"{action=}")
  btn_class=f' {btn_class_list.get(action.get_dict().get("status", "None"),"None")}'
  return f'<button class="btn btn-sm {btn_class}">{action.status.value}</button>'


def generate_stage_steps_html(mf: meta_file.Meta_File, stage : stages.Stage):

  logging.debug(f"Generate HTML for stage {stage.name}")

  actions = stage.actions.get_actions_as_dict()
  
  multi='s'
  if len(actions) == 1:
    multi=''

  if len(actions) == 0:
    logging.warning('No actions found')
    return ''

  html_actions = render_template('overview/details/stage-actions-details.html', file_name=mf.file_name, stage=stage.name, cmds=actions)
  #html_actions = render_template('overview/details/quotes.html', html=html_actions)
  
  html_actions=html_actions.replace('\n', '')
  html_actions=html_actions.replace('\r\n', '')
  html_actions=html_actions.replace('&quot;', '\\&quot;')
  html_actions=html_actions.replace('&#39;', '\\&#39;')

  logging.debug(f"{html_actions=}")

  return html_actions



def generate_steps(mf: meta_file.Meta_File, stage : stages.Stage):

  html = render_template('overview/details/stage-actions.html', file_name=mf.file_name, stage=stage.name)

  return html



def get_flow_stage(mf: meta_file.Meta_File, stage : stages.Stage):

  global flow_stages
  global flow_connection
  
  logging.debug(f"{stage.get_dict()=}")

  flow_stages.append(get_stage_as_html_id(stage.name))

  next_stages = stage.get_next_stages()
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
    sub_row+=get_flow_stage(mf, mf.stages.get_stage(ns.name))
    sub_row+=div_row_end

  # This stage
  html=div_column
  html+= generate_stage_button(mf, stage)
  if mf.status in [meta_file.Meta_file_status.FAILED, meta_file.Meta_file_status.READY] and stage.name in mf.stages.get_runable_stages().get_all_names():
    html+= generate_run_button(mf, stage)

  if len(stage.processing_steps) > 0:
    html+= generate_steps(mf, stage)
  html+=div_column_end
  # Next stages
  html+=div_column
  html+=sub_row
  html+=div_column_end

  return html



def get_flowchar_html(mf: meta_file.Meta_File):

  global flow_stages
  global flow_connection
  flow_connection=[]
  flow_stages=[]
  #mf.workflow.load_workflow_data()

  logging.debug(f"{mf.stages.get_all_names()}")

  html=div_container
  html+=div_row
  html+=get_flow_stage(mf, mf.stages.get_stage('START'))
  html+=div_row_end
  html+=div_container_end
  
  java_script=''
  for fs in flow_stages:
    java_script+=f'\n  let {fs} = document.getElementById("{fs}");'

  for fc in flow_connection:
    java_script+=f'\n  connectItems({fc["from"]}, {fc["to"]}, "{fc["direction_from"]}", "{fc["direction_to"]}");'

  #let Start = document.getElementById("Start");
  #let button2 = document.getElementById("button2");
  #let button3 = document.getElementById("button3");
  #let End = document.getElementById("End");

  #connectItems(Start, button2, "right", "top");
  #connectItems(Start, button3, "bottom", "left");
  #connectItems(Start, End, "right", "top");
  #connectItems(button2, End, "bottom", "left");
  #connectItems(button3, End, "bottom", "left");

  return {'html': html, 'java_script': java_script}




# root=>start: Root
# e=>end: End
# start=>parallel: Start
# uat=>operation: UAT
# archive=>operation: Archive
# 
# root->start
# start(path1, left,bottom)->uat
# start(path2, right,top)->archive
# 
# uat->e
# archive->e

        
#START=>parallel: START
#UAT_TEST=>operation: User Acceptance Tests
#ARCHIV_TEST=>operation: Tests Archiv
#ARCHIV_TEST2=>operation: Tests Archiv 2
#PROD_TEST=>operation: Production
#END=>end: Finished
#
#START(path1@an1,right)->UAT_TEST
#START(path2@an2,bottom)->ARCHIV_TEST
#START(path3@an3,left)->ARCHIV_TEST2
#ARCHIV_TEST->END
#UAT_TEST->END

def get_flowchart_text(mf: meta_file.Meta_File):

  wf_steps = 'start=>start: Start'
  wf_flow = ''
  parallel_directions = ['bottom', 'right', 'top']
  default_step_direction = 'right'
  default_stage_direction = 'bottom'


  mf.workflow.load_workflow_data()
  
  # Fow diagramm for each stage
  for stage in mf.workflow.stages:

    logging.debug(f"{stage=}")

    
    # Get current detailed stage information (status)
    mf_stage = stages.Stage()
    if stage['name'] in mf.stages.get_all_names():
      mf_stage = mf.stages.get_stage(stage['name'])
    
    deploy_objects = []
    for obj in mf.deploy_objects:
      actions = obj.actions.get_actions(stage=stage["name"])
      if len(actions) == 0:
        continue
      deploy_objects.append({'object': obj, 'actions': actions})


    # Always an begin_{stage} + end_{stage}
    operation = 'operation'
    if len(deploy_objects) > 0:
      operation = 'parallel'
    wf_steps += f'\n\nbegin_{stage["name"]}=>{operation}: Begin {stage.get("description", stage["name"])}|stage_{mf_stage.status.value}'

    if wf_flow == '':
      wf_flow=f'\nstart->begin_{stage["name"]}'

    # If mutiple next steps: the end_{stage} must be parallel
    type = 'operation'
    if len(stage.get("next_stages", [])) > 1:
      type='parallel'
    wf_steps += f'\nend_{stage["name"]}=>{type}: End {stage.get("description", stage["name"])}|stage_{mf_stage.status.value}'

    wf_flow += f'\nbegin_{stage["name"]}'

    stage_actions = mf.actions.get_actions(stage=stage["name"])
    stage_obj_actions={}

    stage_parallel_i=1
    first_parallel=f'path{stage_parallel_i},'
    for action in stage_actions:
      logging.debug(f"{action=}")
      wf_steps += f'\n{stage["name"]}_{action.processing_step}=>subroutine: {action.processing_step}|step_{action.status.value}'
      wf_flow += f'({first_parallel}{default_step_direction})->{stage["name"]}_{action.processing_step}'
      first_parallel=''
    wf_flow += f'({default_step_direction})->end_{stage["name"]}'

  
    # Objects can also have actions
    previous_step = f'begin_{stage["name"]}'
    do_parallel=0
    do_i=0
    for do in deploy_objects:

      do_i+=1
      do_parallel+=1

      obj = do['object']
      actions = do['actions']
      
      step_type='operation'
      flow_type=f'path{do_parallel},bottom'

      if len(deploy_objects)>do_i:
        
        flow_type=f'patha{do_parallel},bottom' #!!!! wird nicht gebraucht
        if do_i==1:
          stage_parallel_i+=1
          flow_type=f'path{stage_parallel_i},bottom'

        step_type='parallel'

      obj_step_name = f'{stage["name"]}_{obj.prod_lib}_{obj.name}_{obj.type}'
      wf_steps += f'\nbegin_{obj_step_name}(align-next=no)=>{step_type}: {obj.prod_lib}/{obj.name}.{obj.type} |step_new'
      wf_steps += f'\nend_{obj_step_name}=>operation: {obj.prod_lib}/{obj.name}.{obj.type} |step_new'
      wf_flow += f'\n{previous_step}({flow_type})->begin_{obj_step_name}'
      previous_step = f'begin_{obj_step_name}'
      
      previous_processing = previous_step
      # action.get_dict()={'sequence': 1, 'cmd': 'und noch ein Command', 'status': 'failed', 'stage': 'START', 'processing_step': 'post', 'environment': 'QSYS', 'run_history': [{'create_time': '2023-10-01 09:17:49.753690', 'status': 'failed', 'stdout': 'Command is > und noch ein Command <\nCommand is > dspjoblog <\nCPD000D: Befehl *LIBL/DSPJOBLOG nicht sicher fÃ¼r Job mit mehreren Threads.\n 5770SS1 V7R5M0 220415                        Jobprotokoll anzeigen                SPGV74    01/10/23  09:17:49 CEST    Seite    1\n  Jobname  . . . . . . . . . . :   QP0ZSPWP        Benutzer  . . . . :   QSECOFR      Nummer . . . . . . . . . . . :   461727\n  Jobbeschreibung  . . . . . . :   QDFTSVR         Bibliothek  . . . :   QGPL\nNACHR-ID   ART                     BEW  DATUM     ZEIT             VON PGM      BIBLIOTHEK  INST     AN PGM      BIBLIOTHEK  INST\nCPD000D    Information             30   01/10/23  09:17:49.684765  QCATRS       QSYS        045F     QP2USER2    QSYS        *STMT\n                                     Von Benutzer  . . . . . . . :   PROUZAT1\n                                     Zielmodul . . . . . . . . . :   QP2CL\n                                     Zielprozedur  . . . . . . . :   __Qp2RunCL\n                                     Anweisung . . . . . . . . . :   93\n                                     Nachricht . . . :   Befehl *LIBL/DSPJOBLOG nicht sicher fÃ¼r Job mit mehreren\n                                       Threads.\n                                     Ursache  . . . . :  Der aktuelle Job enthÃ¤lt mehrere Threads. Der Befehl\n                                       *LIBL/DSPJOBLOG kann nicht sicher in einem Job mit mehreren Threads\n                                       ausgefÃ¼hrt werden. Aktion 2 wird ausgefÃ¼hrt. Aktionen: 2 -- Die Verarbeitung\n                                       des Befehls wird fortgesetzt. 3 -- Diese Nachricht folgt auf\n                                       Abbruchnachricht CPF0001. Die Befehlsverarbeitung wird beendet.\n                                       Fehlerbeseitigung:  Der Befehl darf nicht in einem Job mit mehreren Threads\n                                       ausgefÃ¼hrt werden. Technische Beschreibung . . . . . . . :  Befehle, die fÃ¼r\n                                       Threads nicht sicher ausgefÃ¼hrt werden kÃ¶nnen, sollten nicht in einem Job\n                                       mit mehreren Threads benutzt werden. Mit dem Befehl DSPCMD (Befehl anzeigen)\n                                       feststellen, ob ein Befehl sicher fÃ¼r Threads ausgefÃ¼hrt werden kann und\n                                       welche Aktion vom Befehlsanalyseprogramm ausgefÃ¼hrt wird, wenn der Befehl\n                                       fÃ¼r Threads nicht sicher ist. Wurde fÃ¼r die auszufÃ¼hrende Aktion *SYSVAL\n                                       angegeben, wird die vom Befehlsanalyseprogramm durchzufÃ¼hrende Aktion anhand\n                                       des Systemwerts QMLTTHDACN festgelegt.\n', 'stderr': 'CPD0030: Befehl UND in Bibliothek *LIBL nicht gefunden.\nCPF0006: Im Befehl ist ein Fehler aufgetreten.\n'}], 'check_error': False}
      do_a_i=0
      for action in actions:

        do_a_i+=1
        flow_type='right'
        if len(deploy_objects)>do_i and do_a_i == 1:
          flow_type=f'path{do_parallel},right'

        logging.debug(f"{action=}")
        next = f'{stage["name"]}_{obj.prod_lib}_{obj.name}_{obj.type}_{action.processing_step}'
        wf_steps += f'\n{next}(align-next=no)=>subroutine: {obj.prod_lib}/{obj.name}.{obj.type} ({action.processing_step})|step_{action.status.value}'
        wf_flow += f'\n{previous_processing}({flow_type})->{next}'
        previous_processing=next      

    #wf_flow += f'({default_step_direction})->end_{stage["name"]}'

    i=0
    for ns in stage.get("next_stages", []):
      flow_path=f'({default_stage_direction})'
      if step_type=='parallel':
        i+=1
        flow_path = f'(path{i+1},{parallel_directions[i]})'
      wf_flow += f'\nend_{stage["name"]}{flow_path}->begin_{ns}'

      

  return f"{wf_steps}\n{wf_flow}"