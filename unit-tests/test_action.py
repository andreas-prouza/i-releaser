import unittest, json
from modules import deploy_action as da, meta_file, ibm_i_commands
from scripts import save_objects as so
from etc import logger_config, constants


class TestAction(unittest.TestCase):


    def test_actions_and_compare_content(self):

      meta_file1 = meta_file.Meta_File(workflow_name='default', file_name="unit-tests/output/test_action_file_case_1.json", deploy_version=1)
      meta_file1.import_objects_from_config_file('unit-tests/resources/objects.txt')
      meta_file1.load_actions_from_json('unit-tests/resources/object_commands.json')

      commands = ibm_i_commands.IBM_i_commands(meta_file1)
      commands.set_cmds('START')
      
      # Let's run them twice, just to see if multiple run-histories will written
      for i in [1, 2]:
        for stage in meta_file1.current_stages:
          print(f"Run all commands for stage {stage.name}")
          try:
            commands.run_commands(stage=stage.name, processing_step='pre')
            commands.run_commands(stage=stage.name, processing_step='save')
          except Exception as e:
            self.assertEqual(type(e), ibm_i_commands.Command_Exception)

      # Check if they run
      for action in meta_file1.get_actions(stage='START'):
        if action.processing_step not in ['save', 'pre']:
          continue
        self.assertGreaterEqual(len(action.run_history), 1)

      # Load json file to compare
      with open (meta_file1.file_name, "r") as file:
        meta_file1_json=json.load(file)

      # Compare original object and loaded one
      meta_file2 = meta_file.Meta_File.load_json_file(meta_file1.file_name)
      self.assertEqual(meta_file1, meta_file2)

      meta_file2.write_meta_file(update_time=False)
      with open (meta_file1.file_name, "r") as file:
        meta_file2_json=json.load(file)

      # Compare content of real json files
      self.assertEqual(meta_file1_json, meta_file2_json)

      meta1_dict = meta_file1.get_all_data_as_dict()
      meta2_dict = meta_file2.get_all_data_as_dict()

      self.assertEqual(meta1_dict, meta2_dict)



    def test_script_execution(self):
      mf = meta_file.Meta_File(workflow_name='default', file_name="unit-tests/output/test_action_file_case_2.json", deploy_version=1)
      mf.import_objects_from_config_file('unit-tests/resources/objects.txt')
      mf.load_actions_from_json('unit-tests/resources/object_commands.json')

      commands = ibm_i_commands.IBM_i_commands(mf)

      mf.write_meta_file()
      mf.run_current_stages()

      self.assertEqual(mf.get_actions()[0].sequence, 0)
      self.assertEqual(mf.get_actions()[0].stage, 'START')
      self.assertEqual(mf.get_actions()[0].processing_step, 'pre')
      self.assertEqual(mf.get_actions()[0].status, 'finished')
      self.assertEqual(mf.get_actions()[0].run_history[0].status, 'finished')


      mf.write_meta_file()
