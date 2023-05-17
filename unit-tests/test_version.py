import unittest
import time
from modules import meta_file


class TestVersion(unittest.TestCase):


    def test_version(self):

        mf = meta_file.Meta_File(workflow_name='test', file_name="unit-tests/output/test_version_case_1.json")
        mf.import_objects_from_config_file('unit-tests/resources/objects.txt')
        mf.set_status(meta_file.Meta_file_status.READY)
        mf.write_meta_file()

        mf2 = meta_file.Meta_File.load_version(mf.deploy_version)

        mf2.run_current_stage('START')

        self.assertEqual(sorted(['UAT_TEST', 'ARCHIV_TEST']), sorted(mf2.current_stages.get_all_names()))
        self.assertEqual(['START'], mf2.completed_stages.get_all_names())

        mf2.run_current_stages()
        self.assertEqual(sorted(['START', 'UAT_TEST', 'ARCHIV_TEST']), sorted(mf2.completed_stages.get_all_names()))
        self.assertEqual(sorted(['PROD_TEST', 'END']), sorted(mf2.current_stages.get_all_names()))

        mf2.run_current_stages()
        self.assertEqual(sorted(['START', 'UAT_TEST', 'ARCHIV_TEST', 'PROD_TEST', 'END']), sorted(mf2.completed_stages.get_all_names()))
        self.assertEqual(sorted(['END']), sorted(mf2.current_stages.get_all_names()))

        mf2.run_current_stages()
        self.assertEqual([], mf2.current_stages.get_all_names())

