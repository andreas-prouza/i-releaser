from __future__ import annotations
import logging
from modules import meta_file, stages
from modules.cmd_status import Status as Cmd_Status


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

  wf_steps = ''
  wf_flow = ''
  directions = ['bottom', 'right', 'top']
  default_direction = 'right'


  mf.workflow.load_workflow_data()
  
  for stage in mf.workflow.stages:

    logging.debug(f"{stage=}")

    operation = 'operation'
    if stage["name"].lower() in ['start', 'end']:
      operation = stage["name"].lower()
    
    mf_stage = stages.Stage()
    if stage['name'] in mf.stages.get_all_names():
      mf_stage = mf.stages.get_stage(stage['name'])
    
    wf_steps += f'\n\nbegin_{stage["name"]}=>{operation}: Begin {stage.get("description", stage["name"])}|stage_{mf_stage.status.value}'

    if len(stage.get("next_stages", [])) > 1:
      operation='parallel'
    
    wf_steps += f'\nend_{stage["name"]}=>{operation}: End {stage.get("description", stage["name"])}|stage_{mf_stage.status.value}'

    wf_flow += f'\nbegin_{stage["name"]}'

    for action in mf.get_actions(stage=stage["name"]):
      logging.debug(f"{action=}")
      wf_steps += f'\n{stage["name"]}_{action.processing_step}=>subroutine: {action.processing_step}|step_{mf_stage.status.value}'
      wf_flow += f'({default_direction})->{stage["name"]}_{action.processing_step}'
    wf_flow += f'({default_direction})->end_{stage["name"]}'


    i=0
    for ns in stage.get("next_stages", []):
      flow_path=f'({default_direction})'
      if operation=='parallel':
        flow_path = f'(path{i+1},{directions[i]})'
      wf_flow += f'\nend_{stage["name"]}{flow_path}->begin_{ns}'
      i+=1

  return f"{wf_steps}\n{wf_flow}"