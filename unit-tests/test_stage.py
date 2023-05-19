import unittest
#from modules import stages as s
from modules import stages


class TestStage(unittest.TestCase):


    def test_content(self):
        stage = stages.Stage.get_stage('default', 'UAT')
        self.assertIn('PROD', stage.get_next_stages_name())

        next_stages = stages.Stage_List_list('default', stage.next_stages)
        self.assertEqual(len(stage.next_stages), len(next_stages))
        
        # It's not allowed to call Constructor
        self.assertRaises(Exception, stages.Stage, 'xx')

        self.assertRaises(Exception, stages.Stage.get_stage, 'xx')

        # 'ERROR' exists but hast wrong attributes
        self.assertRaises(Exception, stages.Stage.get_stage, 'ERROR')


    def test_content2(self):

        stage_list = ['UAT', 'START', 'PROD']
        stage_obj_list = stages.Stage_List_list('default', stage_list)

        self.assertEqual(len(stage_list), len(stage_obj_list))

        for stage in stage_obj_list:
            self.assertIn(stage.name, stage_list)

        self.assertEqual(stage_list, stage_obj_list.get_all_names())


    def test_content_with_file(self):


        import pickle

        stage_list_1 = ['UAT', 'START', 'PROD']
        stage_list_2 = ['UAT', 'START', 'PROD']
        stages_1 = stages.Stage_List_list('default', stage_list_1)
        stages_2 = stages.Stage_List_list('default', stage_list_2)
        stages_1_1 = stages.Stage_List_list('default', stages_1.get_dict())

        # Not equal because of different timestamps
        self.assertNotEqual(stages_1, stages_2)

        self.assertEqual(stages_1, stages_1_1)


        with open('unit-tests/output/stage-list.1.pkl', 'wb') as out_file:
            pickle.dump(stages_1, out_file)
        with open('unit-tests/output/stage-list.2.pkl', 'wb') as out_file:
            pickle.dump(stages_2, out_file)

#        with open(f'{meta_file_1.file_name}.1.pkl', 'rb') as in_file:
#            meta_file_1_2 = pickle.load(in_file)