"""
Jira integration (see docs/jira.md)

As hook of a workflow:

  "hooks": {
    "deployment_created": ["jira.on_event"],
    "stage_started": ["jira.on_event"],
    ...
  }

As processing step (reports the environment of the stage as successful):

  {"processing_step": "jira_successful", "environment": "SCRIPT", "execute": "jira.report_stage", "check_error": false}
"""
import logging

from modules import meta_file as mf, stages as s
from modules import deploy_action as da
from modules import jira_client



def on_event(event: str, meta_file: mf.Meta_File, stage_obj: s.Stage|None) -> None:
    jira_client.report(event, meta_file, stage_obj)



def report_stage(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:

    if not jira_client.report('stage_finished', meta_file, stage_obj, state='successful'):
        logging.warning(f"Nothing reported to Jira for stage {stage_obj.name}. Check etc/jira.json and the issue key in custom data.")
