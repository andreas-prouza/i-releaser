import unittest
from modules import meta_file, deploy_action as da
from modules import ibm_i_commands as ic
from modules import deploy_action as ct
from scripts import save_objects as so


class TestContent(unittest.TestCase):

    def test_save_load_compare(self):
        meta_file_1 = meta_file.Meta_File(workflow_name='default', file_name="unit-tests/output/test_meta_file_case_1.json", deploy_version=1)
        meta_file_1.import_objects_from_config_file("unit-tests/resources/objects.txt")
        obj=meta_file_1.deploy_objects.get_object('prouzalib', 'date', 'srvpgm')
        obj.actions.add_action(da.Deploy_Action(cmd='CMD1', 
                        sequence=2, 
                        status='finished', 
                        stage='UAT',
                        processing_step='save',
                        environment=ct.Command_Type.QSYS))
        obj.actions.add_action(da.Deploy_Action(cmd='CMD1', 
                        sequence=2, 
                        status='finished', 
                        stage='PROD',
                        processing_step='save',
                        environment=ct.Command_Type.QSYS))

        
        icmd = ic.IBM_i_commands(meta_file_1)
        so.set_init_cmds_for_save(meta_file_1, 'START', 'save')
        so.set_cmd_object_to_savf(meta_file_1, 'START', 'save')
        meta_file_1.write_meta_file()

        meta_file_1_list = meta_file_1.get_all_data_as_dict()

        meta_file_2 = meta_file.Meta_File.load_json_file(meta_file_1.file_name)
        meta_file_2_list = meta_file_2.get_all_data_as_dict()
        self.assertGreater(len(meta_file_2.actions.get_list()), 2)
        self.assertEqual(meta_file_1_list, meta_file_2_list)

        obj2=meta_file_2.deploy_objects.get_object('prouzalib', 'date', 'srvpgm')
        action_list = [{
                    "sequence": 2,
                    "cmd": "CMD1",
                    "status": "finished",
                    "stage": "UAT",
                    "processing_step": "save",
                    "environment": "QSYS",
                    "run_history": [],
                    "check_error": True
                },
                {
                    "sequence": 2,
                    "cmd": "CMD1",
                    "status": "finished",
                    "stage": "PROD",
                    "processing_step": "save",
                    "environment": "QSYS",
                    "run_history": [],
                    "check_error": True
                }
        ]
        obj_actions = obj.actions.get_list()
        obj2_actions = obj2.actions.get_list()
        for al in action_list:
            self.assertIn(al, obj_actions)
            self.assertIn(al, obj2_actions)



    def test_load_from_json(self):

        self.assertRaises(Exception, meta_file.Meta_File.load_json_file, '/does/not/exist.json')




