import unittest
from modules import meta_file, deploy_action as da
from modules import ibm_i_commands as ic


class TestContent(unittest.TestCase):

    def test_save_load_compare(self):
        meta_file_1 = meta_file.Meta_File("unit-tests/output/test_meta_file_name_1.json", deploy_version=1)
        meta_file_1.import_objects_from_config_file("unit-tests/resources/objects.txt")
        obj=meta_file_1.deploy_objects.get_object('prouzalib', 'date', '*srvpgm')
        obj.actions.add_action(da.Deploy_Action(cmd='CMD1', sequence=2, status='finished'))
        
        icmd = ic.IBM_i_commands(meta_file_1)
        icmd.set_init_cmds()
        icmd.set_save_objects_cmd()
        meta_file_1.write_meta_file()

        meta_file_1_list = meta_file_1.get_all_data_as_dict()
        del meta_file_1_list["general"]["update_time"]

        meta_file_2 = meta_file.Meta_File.load_json_file(meta_file_1.file_name)
        meta_file_2_list = meta_file_2.get_all_data_as_dict()
        del meta_file_2_list["general"]["update_time"]

        self.assertEqual(len(meta_file_2.actions.get_list()), 8)
        self.assertEqual(meta_file_1_list, meta_file_2_list)

    def test_content(self):
        meta_file_1 = meta_file.Meta_File("unit-tests/output/test_meta_file_name_2.json", deploy_version=2)
        meta_file_1.import_objects_from_config_file("unit-tests/resources/objects.txt")
        meta_file_1_list = meta_file_1.get_all_data_as_dict()
        del meta_file_1_list["general"]["create_time"]
        del meta_file_1_list["general"]["update_time"]

        asume_data_list = {
                "general": {
                    "deploy_version": 2,
                    "file_name": "unit-tests/output/test_meta_file_name_2.json",
                    "status": "new"
                },
                "deploy_libs": {
                    "main_lib": "d000000002",
                    "backup_lib": "b000000002",
                    "object_libs": [
                        "prouza2",
                        "prouzalib"
                    ]
                },
                "deploy_cmds": [],
                "objects": [
                    {
                        "obj_lib": "prouza2",
                        "obj_name": "testlog",
                        "obj_type": "*pgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouza2",
                        "obj_name": "cpysrc2ifs",
                        "obj_type": "*srvpgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouza2",
                        "obj_name": "date",
                        "obj_type": "*srvpgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouzalib",
                        "obj_name": "cpysrc2ifs",
                        "obj_type": "*pgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouzalib",
                        "obj_name": "testlog2",
                        "obj_type": "*pgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouzalib",
                        "obj_name": "testsqlerr",
                        "obj_type": "*pgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouzalib",
                        "obj_name": "date",
                        "obj_type": "*srvpgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    },
                    {
                        "obj_lib": "prouzalib",
                        "obj_name": "errhdlsql",
                        "obj_type": "*srvpgm",
                        "deploy_status": "in preperation",
                        "actions": []
                    }
                ]
            }

        # self.maxDiff = None
        self.assertEqual(meta_file_1_list, asume_data_list)
