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