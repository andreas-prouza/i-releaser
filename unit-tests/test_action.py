import unittest, json
from modules import deploy_action as da, meta_file, ibm_i_commands
from etc import constants


class TestAction(unittest.TestCase):


    def test_content(self):

      meta_file1 = meta_file.Meta_File("unit-tests/output/test_action_file_case_1.json", deploy_version=1)
      meta_file1.import_objects_from_config_file('unit-tests/resources/objects.txt')
      meta_file1.load_actions_from_json('unit-tests/resources/object_commands.json')

      commands = ibm_i_commands.IBM_i_commands(meta_file1)
      commands.set_init_cmds_for_save('START')
      commands.set_cmd_object_to_savf('START')
      commands.set_init_cmds_for_deployment('START')

      for stage in meta_file1.current_stages:
        print(f"Run all commands for stage {stage.name}")
        commands.run_commands(da.Processing_Step.SAVE, stage=stage.name)

      with open (meta_file1.file_name, "r") as file:
        meta_file1_json=json.load(file)
      del meta_file1_json["general"]["update_time"]

      meta_file2 = meta_file.Meta_File.load_json_file(meta_file1.file_name)
      meta_file2.write_meta_file()

      with open (meta_file1.file_name, "r") as file:
        meta_file2_json=json.load(file)
      del meta_file2_json["general"]["update_time"]

      # Compare content of real json files
      self.assertEqual(meta_file1_json, meta_file2_json)


      meta1_dict = meta_file1.get_all_data_as_dict()
      del meta1_dict["general"]["update_time"]
      meta2_dict = meta_file2.get_all_data_as_dict()
      del meta2_dict["general"]["update_time"]

      self.assertEqual(meta1_dict, meta2_dict)
