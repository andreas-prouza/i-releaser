import unittest
import time
from modules import meta_file


class TestWorkflow(unittest.TestCase):


    def test_validation(self):

        mf = meta_file.Meta_File(workflow_name='test', file_name="unit-tests/output/test_workflow_case_1.json")
        mf.import_objects_from_config_file('unit-tests/resources/objects.txt')
        mf.set_status(meta_file.Meta_file_status.READY)
        mf.write_meta_file()

        self.assertRaises(Exception, meta_file.Meta_File, workflow_name='does not exist')
        
        self.assertRaises(Exception, meta_file.Meta_File, workflow_name='test_attributes')

