import json, os
import logging
from typing import List

from etc import constants
from modules import errors, files, json_path, hooks
import glob


class MissingProcessingStepMappingException(Exception):
  pass

class WorkflowNotFoundException(errors.Not_Found_Error):
  pass

class StageRecursionException(Exception):
  pass



class Workflow:
  """Stored information of an workflow
  Attributes
  ----------
  name : str
      Name of the workflow
  step_action : list
      A list of steps and the related scripts to run fo that step
  stages : list
      A list of stages for this workflow
  ----------
  """

  name: str|None

  # Custom data which can't be set when a deployment is created, unless the workflow allows it with `create_fields`
  PROTECTED_CUSTOM_DATA = ['db_deployment']
  

  def __init__(self, name: str|None=None, dict: dict|None=None):

    self.name = name.lower() if name else None
    self.object_commands = []
    self.default_project = None
    self.step_action = None
    self.stages = None
    self.parallel_deployment_execution_allowed: bool = False
    self.editable_fields: List[str] = []
    self.create_fields: List[str]|None = None
    self.hooks: dict[str, List[str]] = {}

    #logging.debug(f"{name=}, {dict=}")

    if dict is not None and len(dict) > 0:

      self.name = dict['name'].lower()
      
      if 'step_action' in dict:
        self.step_action = dict['step_action']

      if 'default_project' in dict:
        self.default_project = dict['default_project']

      if 'stages' in dict:
        self.stages = dict['stages']
      
      if 'parallel_deployment_execution_allowed' in dict:
        self.parallel_deployment_execution_allowed = dict['parallel_deployment_execution_allowed']

      if 'editable_fields' in dict:
        self.editable_fields = dict['editable_fields'] or []

      if 'create_fields' in dict:
        self.create_fields = dict['create_fields']

      if 'hooks' in dict:
        self.hooks = dict['hooks'] or {}

      #logging.debug(f"Workflow created from dict: {self.get_dict()}")

      return

    #logging.debug(f"Dict is None: {dict=} {name=}")
    self.load_workflow_data()
    logging.debug("Workflow loaded")
    #self.step_action = self.get_workflow_steps_mapping()



  def load_workflow_data(self) -> None:

    if not self.name:
      raise Exception(f"No workflow name provided for loading workflow data!")
    wf = self.get_workflow_by_name(self.name)
    self.__dict__.update(wf.__dict__)
    logging.debug(f"Workflow data loaded for workflow {self.get_dict()}!")



  @staticmethod
  def get_default_step_mapping() -> List[dict]|None:

    step_mapping_json = files.getJson(constants.C_DEFAULT_STEP_ACTION)
    return step_mapping_json
  


  @staticmethod
  def get_workflow_by_name(workflow_name:str) -> 'Workflow':

    workflows_json = Workflow.get_all_workflows_json()

    for wf in workflows_json:

      if workflow_name == wf['name'].lower():
        return Workflow(dict=wf)

    invalid_files = Workflow.get_invalid_workflow_files()
    if len(invalid_files) > 0:
      raise WorkflowNotFoundException(f"No workflow found with name '{workflow_name}'. These workflow files are invalid: {', '.join(os.path.basename(f) for f in invalid_files)}")

    raise WorkflowNotFoundException(f"No workflow found with name '{workflow_name}'")



  @staticmethod
  def get_all_workflows_from_old_workflow_json() -> List[dict]:

    if not os.path.isfile(constants.C_WORKFLOW):
      logging.info(f"No old workflow file found at {constants.C_WORKFLOW}! Very good!")
      return []
    
    import warnings
    warnings.warn(f"DeprecationWarning: Use of old workflow file: {os.path.abspath(constants.C_WORKFLOW)}. Migrate to single etc/workflows/*.json file for each workflow!", DeprecationWarning, stacklevel=2)
    logging.warning(f"Use of old workflow file: {os.path.abspath(constants.C_WORKFLOW)}. Migrate to single etc/workflows/*.json file for each workflow!")

    try:
      workflows_json = files.getJson(constants.C_WORKFLOW, retry=False)
    except Exception as e:
      logging.error(f"Error loading workflow file {constants.C_WORKFLOW}: {e}")
      return []

    return workflows_json




  @staticmethod
  def get_all_projects() -> List[str]:
    
    projects=[]

    workflows_json = Workflow.get_all_workflows_json()

    for wf in workflows_json:
      if wf['default_project'] not in projects:
        projects.append(wf['default_project'])

    return projects



  @staticmethod
  def read_workflow_file(wf_file: str) -> dict:
    """
    Raises:
        Exception: If the file is not a valid workflow
    """

    json_data = files.getJson(wf_file, retry=False, use_cache=False)

    if not isinstance(json_data, dict):
      raise Exception(f"Workflow file contains a {type(json_data)} instead of dict.")

    Workflow.validate_workflow(json_data, wf_file)

    return json_data



  @staticmethod
  def get_workflow_files() -> List[str]:
    return sorted(glob.glob(os.path.join(constants.C_WORKFLOWS_DIR, "*.json")))



  @staticmethod
  def get_all_workflows_json() -> List[dict]:
    """All valid workflows. Invalid files are left out, so they don't affect the other workflows (see get_invalid_workflow_files)."""

    workflows_json = []

    for wf_file in Workflow.get_workflow_files():

      try:
        workflows_json.append(Workflow.read_workflow_file(wf_file))

      except Exception as e:
        logging.error(f"Error loading workflow file {wf_file}: {e}")

    workflows_json += Workflow.get_all_workflows_from_old_workflow_json()

    return workflows_json



  @staticmethod
  def get_invalid_workflow_files() -> dict[str, str]:
    """
    Returns:
        dict: {file name: error}
    """

    invalid_files = {}

    for wf_file in Workflow.get_workflow_files():

      try:
        Workflow.read_workflow_file(wf_file)

      except Exception as e:
        invalid_files[wf_file] = str(e)

    return invalid_files



  def check_custom_data(self, custom_data: dict|None) -> None:
    """
    Checks the custom data a deployment is created with.

    Raises:
        errors.Invalid_Input_Error: If it's too large or contains fields which are not allowed
    """

    if not custom_data:
      return

    if len(json.dumps(custom_data)) > constants.C_MAX_CUSTOM_DATA_SIZE:
      raise errors.Invalid_Input_Error(f"Custom data is larger than {constants.C_MAX_CUSTOM_DATA_SIZE} bytes")

    allowed = None if self.create_fields is None else [json_path.parse(path) for path in self.create_fields]
    invalid_fields = []

    for path in json_path.get_leaf_paths(custom_data):

      if allowed is None:
        is_allowed = len(path) == 0 or path[0] not in Workflow.PROTECTED_CUSTOM_DATA
      else:
        is_allowed = any(json_path.is_under(path, parent) for parent in allowed)

      if not is_allowed and path[0] not in invalid_fields:
        invalid_fields.append(path[0])

    if len(invalid_fields) > 0:
      raise errors.Invalid_Input_Error(f"These custom data fields can't be set when creating a deployment of workflow '{self.name}': {', '.join(str(f) for f in invalid_fields)}")



  def check_object_list(self, object_list: str) -> None:
    """
    An object list has to be in the build_dir of a stage or in C_OBJECT_LIST_DIRS.

    Raises:
        errors.Invalid_Input_Error: If it's somewhere else
    """

    path = os.path.realpath(object_list)
    allowed_dirs = [stage['build_dir'] for stage in self.stages if stage.get('build_dir')] + constants.C_OBJECT_LIST_DIRS

    if not any(path.startswith(os.path.realpath(allowed_dir) + os.sep) for allowed_dir in allowed_dirs):
      raise errors.Invalid_Input_Error(f"Object list '{object_list}' is not in an allowed directory")



  def get_stage(self, stage_name:str) -> dict:
    """
    Retrieves stage dict from workflow.json

    Args:
        stage_name (str): Name of stage
    Returns:
        stage (dict): Stage as dictionary
    """
    if not self.stages:
      logging.info(f"Workflow: {self.get_dict()}")
      error = Exception(f"No stages defined for workflow {self.name}!")
      logging.exception(error, stack_info=True)
      raise error
    
    for stage in self.stages:
      if stage['name'] == stage_name:
        logging.debug(f'Found stage in workflow: {stage=}')
        return stage
      
    error = Exception(f"No stage found for {stage_name}!")
    logging.exception(error, stack_info=True)
    raise error




  @staticmethod
  def get_workflow_steps_mapping(workflow_dict: dict) -> List[dict]:
    """
    Get steps mapping list of the current workflow + the global constants definition

    Returns:
        mapping_lsit (list): List of mappings
    """

    step_mapping: List[dict] = Workflow.get_default_step_mapping() or []

    if 'step_action' in workflow_dict.keys() and workflow_dict['step_action'] is not None:
      logging.debug(f'len {len(step_mapping)=}, {len(workflow_dict["step_action"])=}')
      merged_list = {x['processing_step']:x for x in step_mapping + workflow_dict["step_action"]}.values()
      #logging.debug(f"{merged_list=}")
      return list(merged_list)
    
    return step_mapping




  @staticmethod
  def validate_workflow(workflow_dict: dict, wf_file: str) -> None:

    if 'name' not in workflow_dict.keys():
      raise Exception(f"No workflow name is defined in file {wf_file}!")

    if 'default_project' not in workflow_dict.keys():
      raise Exception(f"No default_project name is defined in file {wf_file}!")

    if 'stages' not in workflow_dict.keys() or len(workflow_dict['stages']) == 0:
      raise Exception(f"No stage definition for workflow {workflow_dict['name']} in file {wf_file}!")

    from modules import stages
    stages.Stage_List_list.validate_items(workflow_dict['stages'])

    for key in workflow_dict.keys():
      if key not in ['name', 'step_action', 'stages', 'default_project', 'parallel_deployment_execution_allowed', 'editable_fields', 'create_fields', 'hooks']:
        raise Exception(f"Workflow attribute '{key}' is invalid in file {wf_file}!")

    for attribute in ['editable_fields', 'create_fields']:
      fields = workflow_dict.get(attribute, [])
      if not isinstance(fields, list):
        raise Exception(f"Workflow attribute '{attribute}' needs to be a list of JSONPaths in file {wf_file}!")
      for field in fields:
        try:
          json_path.parse(field)
        except json_path.InvalidJsonPathException as e:
          raise Exception(f"Invalid entry in '{attribute}' in file {wf_file}: {e}")

    try:
      hooks.validate(workflow_dict.get('hooks', {}))
    except hooks.InvalidHookException as e:
      raise Exception(f"Invalid 'hooks' in file {wf_file}: {e}")
    
    #######################################

    steps_mapping = Workflow.get_workflow_steps_mapping(workflow_dict=workflow_dict)
    for stage in workflow_dict['stages']:
      
      if 'processing_steps' not in stage.keys():
        continue

      for ps in stage['processing_steps']:
        found = False
        for sm in steps_mapping:
          if ps == sm['processing_step']:
            found = True
            break
        if not found:
          raise MissingProcessingStepMappingException(f"No process mapping found for step {ps} in stage {stage['name']}")

    if 'step_action' in workflow_dict.keys():
      script_mappings = workflow_dict['step_action']
      for mapping in script_mappings:
        for key in mapping.keys():
          if key not in ['processing_step', 'environment', 'execute', 'check_error', 'execute_remote', 'fail_on_stderr', 'timeout_seconds', 'parallel_group', 'parallel']:
            raise Exception(f"Script-Mapping attribute '{key}' is invalid for workflow {workflow_dict['name']} in file {wf_file}!")

    ########################################

    Workflow.check_worfklow_loop(workflow_dict['stages'], wf_file=wf_file)




  @staticmethod
  def check_worfklow_loop(workflow_stages: List[dict], start_stage :str='START', counter :int=1, wf_file: str='') -> None:

    if counter >= 200:
      raise(StageRecursionException(f'Infinite loop ({counter}) in next_stage configuration: {workflow_stages=} in file {wf_file}'))

    for stage in workflow_stages:
      if stage['name'] == start_stage:
        for next_stage in stage.get('next_stages', []):
          counter += 1
          Workflow.check_worfklow_loop(
              workflow_stages=workflow_stages, 
              start_stage=next_stage, 
              counter=counter,
              wf_file=wf_file)






  def get_dict(self) -> dict:
    return {
      'name': self.name,
      'step_action': self.step_action,
      'object_commands': self.object_commands,
      'default_project': self.default_project,
      'stages': self.stages,
      'editable_fields': self.editable_fields,
      'create_fields': self.create_fields,
      'hooks': self.hooks
    }



  def __eq__(self, o):
    if self.name == o.name and self.step_action == o.step_action:
      return True
    return False