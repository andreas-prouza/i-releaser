import unittest
from modules import meta_file, deploy_action as da
from modules import ibm_i_commands as ic
from modules import deploy_action as ct


class TestContent(unittest.TestCase):

    def test_save_load_compare(self):
        meta_file_1 = meta_file.Meta_File("unit-tests/output/test_meta_file_case_1.json", deploy_version=1)
        meta_file_1.import_objects_from_config_file("unit-tests/resources/objects.txt")
        obj=meta_file_1.deploy_objects.get_object('prouzalib', 'date', 'srvpgm')
        obj.actions.add_action(da.Deploy_Action(cmd='CMD1', 
                        sequence=2, 
                        status='finished', 
                        stage='UAT',
                        processing_step=ct.Processing_Step.SAVE,
                        environment=ct.Command_Type.QSYS))
        obj.actions.add_action(da.Deploy_Action(cmd='CMD1', 
                        sequence=2, 
                        status='finished', 
                        stage='PROD',
                        processing_step=ct.Processing_Step.SAVE,
                        environment=ct.Command_Type.QSYS))

        
        meta_file_1.write_meta_file()
        icmd = ic.IBM_i_commands(meta_file_1)
        icmd.set_init_cmds_for_save('START')
        icmd.set_cmd_object_to_savf('START')
        meta_file_1.write_meta_file()

        meta_file_1_list = meta_file_1.get_all_data_as_dict()
        del meta_file_1_list["general"]["update_time"]

        meta_file_2 = meta_file.Meta_File.load_json_file(meta_file_1.file_name)
        meta_file_2_list = meta_file_2.get_all_data_as_dict()
        del meta_file_2_list["general"]["update_time"]

        self.assertEqual(len(meta_file_2.actions.get_list()), 9)
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




    def test_content(self):
        meta_file_1 = meta_file.Meta_File("unit-tests/output/test_meta_file_case_2.json", deploy_version=2)
        meta_file_1.import_objects_from_config_file("unit-tests/resources/objects.txt")
        meta_file_1.load_actions_from_json("unit-tests/resources/object_commands.json")
        meta_file_1.write_meta_file()
        meta_file_1_list = meta_file_1.get_all_data_as_dict()
        del meta_file_1_list["general"]["create_time"]
        del meta_file_1_list["general"]["update_time"]
        del meta_file_1_list["general"]["current_stages"][0]["create_time"]

        asume_data_list = {
                "general": {
                    "deploy_version": 2,
                    "file_name": "unit-tests/output/test_meta_file_case_2.json",
                    "status": "new",
                    "current_stages": [
                        {
                            "name": "START",
                            "description": None,
                            "host": None,
                            "next_stages": [
                                "UAT",
                                "ARCHIV"
                            ],
                            "clear_files": True,
                            "lib_replacement_necessary": None,
                            "lib_mapping": [],
                            "status": None,
                            "update_time": None
                        }
                    ]
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
            "obj_prod_lib": "prouzalib",
            "obj_name": "testlog",
            "obj_type": "pgm",
            "obj_attribute": "rpgle",
            "deploy_status": "in preperation",
            "actions": [
                {
                    "sequence": 0,
                    "cmd": "test cmd 1",
                    "status": "new",
                    "stage": "START",
                    "processing_step": "post",
                    "environment": "QSYS",
                    "run_history": [],
                    "check_error": True
                }
            ]
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "logger",
            "obj_type": "file",
            "obj_attribute": "sqltable",
            "deploy_status": "in preperation",
            "actions": []
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "cpysrc2ifs",
            "obj_type": "pgm",
            "obj_attribute": "sqlrpgle",
            "deploy_status": "in preperation",
            "actions": []
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "testlog2",
            "obj_type": "pgm",
            "obj_attribute": "sqlrpgle",
            "deploy_status": "in preperation",
            "actions": []
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "testsqlerr",
            "obj_type": "pgm",
            "obj_attribute": "sqlrpgle",
            "deploy_status": "in preperation",
            "actions": []
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "date",
            "obj_type": "srvpgm",
            "obj_attribute": "sqlrpgle",
            "deploy_status": "in preperation",
            "actions": [
                {
                    "sequence": 0,
                    "cmd": "hier ein Command aus der JSON Konfig",
                    "status": "new",
                    "stage": "START",
                    "processing_step": "save",
                    "environment": "QSYS",
                    "run_history": [],
                    "check_error": True
                },
                {
                    "sequence": 1,
                    "cmd": "und noch ein Command",
                    "status": "new",
                    "stage": "START",
                    "processing_step": "post",
                    "environment": "QSYS",
                    "run_history": [],
                    "check_error": True
                }
            ]
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "errhdlsql",
            "obj_type": "srvpgm",
            "obj_attribute": "sqlrpgle",
            "deploy_status": "in preperation",
            "actions": []
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "logger",
            "obj_type": "srvpgm",
            "obj_attribute": "sqlrpgle",
            "deploy_status": "in preperation",
            "actions": []
        },
        {
            "obj_lib": "prouzalib",
            "obj_prod_lib": "prouzalib",
            "obj_name": "testmod",
            "obj_type": "srvpgm",
            "obj_attribute": "rpgle",
            "deploy_status": "in preperation",
            "actions": []
        }
    ]
            }

        # self.maxDiff = None
        self.assertEqual(meta_file_1_list, asume_data_list)
