import unittest, sys, os
from types import SimpleNamespace
from unittest.mock import patch, Mock

# The repository root, so `etc` and `modules` are found
sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from modules import hooks, workflow


def get_workflow_dict(**kwargs) -> dict:
    wf = {
        'name': 'hook_wf',
        'default_project': 'test',
        'stages': [
            {'name': 'START', 'next_stages': ['END']},
            {'name': 'END'},
        ],
    }
    wf.update(kwargs)
    return wf



class TestHooks(unittest.TestCase):


    @patch.object(workflow.Workflow, 'get_default_step_mapping', return_value=[])
    def test_validate_workflow(self, _):

        workflow.Workflow.validate_workflow(get_workflow_dict(), 'test.json')
        workflow.Workflow.validate_workflow(get_workflow_dict(hooks={'stage_finished': ['jira.on_event'], 'deployment_created': []}), 'test.json')

        for invalid in [
            ['jira.on_event'],                        # no dict
            {'stage_done': ['jira.on_event']},        # unknown event
            {'stage_finished': 'jira.on_event'},      # no list
            {'stage_finished': ['jira']},             # no function
            {'stage_finished': ['scripts.jira.on_event']},
            {'stage_finished': ['.on_event']},
            {'stage_finished': [1]},
        ]:
            with self.subTest(hooks=invalid):
                self.assertRaises(Exception, workflow.Workflow.validate_workflow, get_workflow_dict(hooks=invalid), 'test.json')


    def test_workflow_dict(self):

        wf_hooks = {'stage_finished': ['jira.on_event']}
        wf = workflow.Workflow(dict=get_workflow_dict(hooks=wf_hooks))

        self.assertEqual(wf.hooks, wf_hooks)
        # Stored with each deployment
        self.assertEqual(workflow.Workflow(dict=wf.get_dict()).hooks, wf_hooks)
        # Workflows without hooks
        self.assertEqual(workflow.Workflow(dict=get_workflow_dict()).hooks, {})


    def test_emit(self):

        handler = Mock()
        other = Mock()
        meta_file = SimpleNamespace(workflow=SimpleNamespace(hooks={'stage_finished': ['jira.on_event', 'other.run']}))
        stage = SimpleNamespace(name='BUILD')

        with patch.object(hooks.importlib, 'import_module', side_effect=lambda name: {'scripts.jira': SimpleNamespace(on_event=handler), 'scripts.other': SimpleNamespace(run=other)}[name]):
            hooks.emit(hooks.Event.STAGE_FINISHED, meta_file, stage)
            hooks.emit(hooks.Event.STAGE_STARTED, meta_file, stage)

        handler.assert_called_once_with('stage_finished', meta_file, stage)
        other.assert_called_once_with('stage_finished', meta_file, stage)


    def test_emit_never_raises(self):

        failing = Mock(side_effect=Exception('Jira is down'))
        called = Mock()
        meta_file = SimpleNamespace(workflow=SimpleNamespace(hooks={'deployment_created': ['jira.on_event', 'missing.function', 'other.run']}))

        def import_module(name):
            if name == 'scripts.missing':
                raise ModuleNotFoundError(name)
            return SimpleNamespace(on_event=failing, run=called)

        with patch.object(hooks.importlib, 'import_module', side_effect=import_module):
            with self.assertLogs(level='ERROR'):
                hooks.emit(hooks.Event.DEPLOYMENT_CREATED, meta_file)

        failing.assert_called_once_with('deployment_created', meta_file, None)
        # Following hooks still run
        called.assert_called_once_with('deployment_created', meta_file, None)


    def test_emit_without_hooks(self):

        # Deployments created before hooks were added
        hooks.emit(hooks.Event.STAGE_FINISHED, SimpleNamespace(workflow=SimpleNamespace(hooks={})))
        hooks.emit(hooks.Event.STAGE_FINISHED, SimpleNamespace(workflow=SimpleNamespace()))



if __name__ == '__main__':
    unittest.main()
