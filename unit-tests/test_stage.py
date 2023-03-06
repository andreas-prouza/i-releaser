import unittest
from modules import stages as s


class TestStage(unittest.TestCase):


    def test_content(self):
        stage = s.Stage.get_stage('UAT')
        self.assertIn('PROD', stage.get_next_stages_name())

        next_stages = s.Stage_List_list(stage.next_stages)
        self.assertEqual(len(stage.next_stages), len(next_stages))
        
        # It's not allowed to call Constructor
        self.assertRaises(Exception, s.Stage, 'xx')

        self.assertRaises(Exception, s.Stage.get_stage, 'xx')

        # 'ERROR' exists but hast wrong attributes
        self.assertRaises(Exception, s.Stage.get_stage, 'ERROR')


    def test_content2(self):

        stage_list = ['UAT', 'START', 'PROD']
        stages = s.Stage_List_list(stage_list)

        self.assertEqual(len(stage_list), len(stages))

        for stage in stages:
            self.assertIn(stage.name, stage_list)

        self.assertEqual(stage_list, stages.get_all_names())


    def test_content_with_file(self):


        import pickle
        
        stage_list_1 = ['UAT', 'START', 'PROD']
        stage_list_2 = ['UAT', 'START', 'PROD']
        stages_1 = s.Stage_List_list(stage_list_1)
        stages_2 = s.Stage_List_list(stage_list_2)
        stages_1_1 = s.Stage_List_list(stages_1.get_dict())

        # Not equal because of different timestamps
        self.assertNotEqual(stages_1, stages_2)

        self.assertEqual(stages_1, stages_1_1)


        with open('stage-list.1.pkl', 'wb') as out_file:
            pickle.dump(stages_1, out_file)
        with open('stage-list.2.pkl', 'wb') as out_file:
            pickle.dump(stages_2, out_file)

#        with open(f'{meta_file_1.file_name}.1.pkl', 'rb') as in_file:
#            meta_file_1_2 = pickle.load(in_file)