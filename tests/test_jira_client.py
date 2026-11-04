import unittest, sys, os
from types import SimpleNamespace
from unittest.mock import patch, Mock

# The repository root, so `etc` and `modules` are found
sys.path.insert(0, os.path.realpath(f"{os.path.dirname(__file__)}/.."))

from modules import jira_client
from modules.jira_client import JiraException
from modules.meta_file_status import Meta_file_status
from modules.stage_status import Status as Stage_Status



ENVIRONMENTS = {
    'BUILD': {'id': 'build', 'display_name': 'Build', 'type': 'development'},
    'DEPLOY_PROD': {'id': 'prod', 'display_name': 'Production', 'type': 'production'},
    'NOT_IN_WORKFLOW': {'id': 'other'},
}


def get_config(**kwargs) -> dict:
    config = {
        'enabled': True,
        'mode': 'cloud',
        'i_releaser_url': 'https://ireleaser.example.com/',
        'cloud': {'cloud_id': 'cloud-1', 'client_id': 'client', 'client_secret': 'secret'},
        'datacenter': {'base_url': 'https://jira.example.com', 'token': 'pat'},
        'workflows': {'Simple_WF': {'environments': ENVIRONMENTS}},
    }
    config.update(kwargs)
    return config


def get_stage(name: str, status=Stage_Status.NEW):
    return SimpleNamespace(name=name, status=status)


def get_meta_file(status=Meta_file_status.READY, custom_data=None, stages=None):
    return SimpleNamespace(
        id=42, project='test', deploy_version=7, status=status,
        workflow=SimpleNamespace(name='simple_wf'),
        custom_data={'jira': {'ticket': 'ABC-1'}} if custom_data is None else custom_data,
        stages=stages if stages is not None else [get_stage('START', Stage_Status.READY), get_stage('BUILD'), get_stage('DEPLOY_PROD'), get_stage('END')],
    )


def get_response(status_code=200, json=None):
    return Mock(status_code=status_code, ok=status_code < 400, content=b'{}', text='error text', json=Mock(return_value=json or {}))


def token_or_bulk(url, **kwargs):
    if url.endswith('/oauth/token'):
        return get_response(json={'access_token': 'token-1', 'expires_in': 3600})
    return get_response(202, {'acceptedDeployments': []})



class TestJiraClient(unittest.TestCase):


    def setUp(self):
        jira_client._Cache.token = None
        jira_client._Cache.token_expires = 0
        jira_client._Cache.cloud_id = None


    def test_issue_keys(self):

        config = get_config()

        for custom_data, expected in [
            ({'jira': {'ticket': 'ABC-1'}}, ['ABC-1']),
            ({'jira': {'ticket': 'abc-1'}}, ['ABC-1']),
            ({'jira': {'ticket': 'ABC-1, DEF_2-20,ABC-1'}}, ['ABC-1', 'DEF_2-20']),
            ({'jira': {'ticket': ['ABC-1', 'DEF-2']}}, ['ABC-1', 'DEF-2']),
            ({'jira': {'ticket': ''}}, []),
            ({'jira': {'ticket': None}}, []),
            ({'jira': {}}, []),
            ({}, []),
            (None, []),
        ]:
            with self.subTest(custom_data=custom_data):
                self.assertEqual(jira_client.get_issue_keys(config, custom_data), expected)

        with self.assertLogs(level='WARNING'):
            self.assertEqual(jira_client.get_issue_keys(config, {'jira': {'ticket': 'no ticket, ABC-1'}}), ['ABC-1'])

        config = get_config(issue_key_paths=['$.ticket', '$.jira.tickets'])
        self.assertEqual(jira_client.get_issue_keys(config, {'ticket': 'ABC-1', 'jira': {'tickets': ['DEF-2']}}), ['ABC-1', 'DEF-2'])


    def test_state(self):

        mf = get_meta_file()
        for status, expected in [
            (Stage_Status.NEW, 'pending'),
            (Stage_Status.READY, 'pending'),
            (Stage_Status.IN_PROCESS, 'in_progress'),
            ('in process', 'in_progress'),
            (Stage_Status.FAILED, 'failed'),
            (Stage_Status.FINISHED, 'successful'),
        ]:
            with self.subTest(status=status):
                self.assertEqual(jira_client.get_state('stage_started', mf, get_stage('BUILD', status)), expected)

        # Error which didn't set the stage status to failed
        self.assertEqual(jira_client.get_state('stage_failed', mf, get_stage('BUILD', Stage_Status.IN_PROCESS)), 'failed')

        canceled = get_meta_file(status=Meta_file_status.CANCELED)
        self.assertEqual(jira_client.get_state('deployment_canceled', canceled, get_stage('BUILD', Stage_Status.NEW)), 'cancelled')
        self.assertEqual(jira_client.get_state('deployment_canceled', canceled, get_stage('BUILD', Stage_Status.FINISHED)), 'successful')


    @patch.object(jira_client.requests, 'post')
    def test_nothing_to_report(self, post):

        for config, meta_file, stage in [
            (None, get_meta_file(), None),
            (get_config(enabled=False), get_meta_file(), None),
            (get_config(workflows={}), get_meta_file(), None),
            (get_config(), get_meta_file(), get_stage('START')),
            (get_config(), get_meta_file(custom_data={}), get_stage('BUILD')),
        ]:
            with self.subTest(config=config, stage=stage), patch.object(jira_client, 'load_config', return_value=config):
                self.assertFalse(jira_client.report('stage_started', meta_file, stage))

        post.assert_not_called()


    @patch.object(jira_client.requests, 'post', side_effect=token_or_bulk)
    def test_cloud_stage_event(self, post):

        mf = get_meta_file()
        stage = get_stage('BUILD', Stage_Status.IN_PROCESS)

        with patch.object(jira_client, 'load_config', return_value=get_config()):
            self.assertTrue(jira_client.report('stage_started', mf, stage))
            stage.status = Stage_Status.FINISHED
            self.assertTrue(jira_client.report('stage_finished', mf, stage))

        # Token is fetched only once
        urls = [c.args[0] for c in post.call_args_list]
        self.assertEqual(urls, [
            'https://api.atlassian.com/oauth/token',
            'https://api.atlassian.com/jira/deployments/0.1/cloud/cloud-1/bulk',
            'https://api.atlassian.com/jira/deployments/0.1/cloud/cloud-1/bulk',
        ])
        self.assertEqual(post.call_args_list[0].kwargs['json'], {'audience': 'api.atlassian.com', 'grant_type': 'client_credentials', 'client_id': 'client', 'client_secret': 'secret'})

        started = post.call_args_list[1].kwargs['json']['deployments'][0]
        finished = post.call_args_list[2].kwargs
        self.assertEqual(finished['headers'], {'Authorization': 'Bearer token-1'})
        finished = finished['json']['deployments'][0]

        self.assertEqual(started['state'], 'in_progress')
        self.assertEqual(finished['state'], 'successful')
        self.assertGreater(finished['updateSequenceNumber'], started['updateSequenceNumber'])

        self.assertEqual(finished['deploymentSequenceNumber'], 42)
        self.assertEqual(finished['associations'], [{'associationType': 'issueIdOrKeys', 'values': ['ABC-1']}])
        self.assertEqual(finished['displayName'], 'test 7')
        self.assertEqual(finished['label'], '7')
        self.assertEqual(finished['url'], 'https://ireleaser.example.com/show_details/42')
        self.assertEqual(finished['pipeline'], {'id': 'simple_wf', 'displayName': 'simple_wf', 'url': 'https://ireleaser.example.com/workflows'})
        self.assertEqual(finished['environment'], {'id': 'build', 'displayName': 'Build', 'type': 'development'})
        self.assertRegex(finished['lastUpdated'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')


    @patch.object(jira_client.requests, 'post', side_effect=token_or_bulk)
    def test_cloud_deployment_event(self, post):

        mf = get_meta_file()

        with patch.object(jira_client, 'load_config', return_value=get_config()):
            jira_client.report('deployment_created', mf)

            mf.stages[1].status = Stage_Status.FINISHED
            mf.status = Meta_file_status.CANCELED
            jira_client.report('deployment_canceled', mf)

        created = post.call_args_list[1].kwargs['json']['deployments']
        canceled = post.call_args_list[2].kwargs['json']['deployments']

        # All mapped environments of the deployment
        self.assertEqual([(d['environment']['id'], d['state']) for d in created], [('build', 'pending'), ('prod', 'pending')])
        self.assertEqual([(d['environment']['id'], d['state']) for d in canceled], [('build', 'successful'), ('prod', 'cancelled')])


    @patch.object(jira_client.requests, 'get', return_value=get_response(json={'cloudId': 'cloud-from-site'}))
    @patch.object(jira_client.requests, 'post', side_effect=token_or_bulk)
    @patch.dict(os.environ, {jira_client.C_ENV_CLIENT_SECRET: 'secret-from-env'})
    def test_cloud_config(self, post, get):

        config = get_config(cloud={'site': 'company.atlassian.net', 'client_id': 'client', 'client_secret': 'secret', 'api_url': 'http://localhost:8765/'})

        with patch.object(jira_client, 'load_config', return_value=config):
            jira_client.report('stage_started', get_meta_file(), get_stage('BUILD'))
            jira_client.report('stage_started', get_meta_file(), get_stage('BUILD'))

        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], 'https://company.atlassian.net/_edge/tenant_info')
        self.assertEqual(post.call_args_list[0].kwargs['json']['client_secret'], 'secret-from-env')
        self.assertEqual(post.call_args.args[0], 'http://localhost:8765/jira/deployments/0.1/cloud/cloud-from-site/bulk')


    def test_cloud_errors(self):

        with patch.object(jira_client, 'load_config', return_value=get_config()):

            with patch.object(jira_client.requests, 'post', side_effect=lambda url, **kwargs: get_response(401) if url.endswith('/bulk') else token_or_bulk(url)):
                self.assertRaises(JiraException, jira_client.report, 'stage_started', get_meta_file(), get_stage('BUILD'))
            # Token will be fetched again
            self.assertIsNone(jira_client._Cache.token)

            with patch.object(jira_client.requests, 'post', return_value=get_response(401)):
                self.assertRaises(JiraException, jira_client.report, 'stage_started', get_meta_file(), get_stage('BUILD'))

        with patch.object(jira_client, 'load_config', return_value=get_config(cloud={'cloud_id': 'cloud-1'})):
            self.assertRaises(JiraException, jira_client.report, 'stage_started', get_meta_file(), get_stage('BUILD'))

        with patch.object(jira_client, 'load_config', return_value=get_config(mode='server')):
            self.assertRaises(JiraException, jira_client.report, 'stage_started', get_meta_file(), get_stage('BUILD'))


    @patch.object(jira_client.requests, 'post', return_value=get_response(201))
    def test_datacenter(self, post):

        mf = get_meta_file(custom_data={'jira': {'ticket': 'ABC-1, DEF-2'}})

        with patch.object(jira_client, 'load_config', return_value=get_config(mode='datacenter')):
            jira_client.report('stage_started', mf, get_stage('BUILD', Stage_Status.IN_PROCESS))
            self.assertEqual([c.args[0] for c in post.call_args_list], [
                'https://jira.example.com/rest/api/2/issue/ABC-1/remotelink',
                'https://jira.example.com/rest/api/2/issue/DEF-2/remotelink',
            ])

            post.reset_mock()
            jira_client.report('stage_finished', mf, get_stage('DEPLOY_PROD', Stage_Status.FINISHED))

        self.assertEqual([c.args[0] for c in post.call_args_list], [
            'https://jira.example.com/rest/api/2/issue/ABC-1/remotelink',
            'https://jira.example.com/rest/api/2/issue/ABC-1/comment',
            'https://jira.example.com/rest/api/2/issue/DEF-2/remotelink',
            'https://jira.example.com/rest/api/2/issue/DEF-2/comment',
        ])
        self.assertEqual(post.call_args.kwargs['headers'], {'Authorization': 'Bearer pat'})

        link = post.call_args_list[0].kwargs['json']
        self.assertEqual(link['globalId'], 'i-releaser:42:prod')
        self.assertEqual(link['object']['url'], 'https://ireleaser.example.com/show_details/42')
        self.assertEqual(link['object']['title'], 'test 7 - Production: successful')
        self.assertEqual(link['object']['status'], {'resolved': True})

        comment = post.call_args_list[1].kwargs['json']['body']
        self.assertIn('[test 7|https://ireleaser.example.com/show_details/42]', comment)
        self.assertIn('* Production: *successful* (stage DEPLOY_PROD)', comment)


    def test_datacenter_errors(self):

        mf = get_meta_file(custom_data={'jira': {'ticket': 'ABC-1, DEF-2'}})
        config = get_config(mode='datacenter', datacenter={'base_url': 'https://jira.example.com', 'token': 'pat', 'remote_link': True, 'comment_events': []})

        # Unknown issue doesn't stop the other issues
        with patch.object(jira_client, 'load_config', return_value=config), \
             patch.object(jira_client.requests, 'post', side_effect=[get_response(404), get_response(201)]) as post:
            self.assertRaises(JiraException, jira_client.report, 'stage_finished', mf, get_stage('BUILD'))
        self.assertEqual(post.call_count, 2)

        with patch.object(jira_client, 'load_config', return_value=get_config(mode='datacenter', datacenter={'base_url': 'https://jira.example.com'})), \
             patch.dict(os.environ, {}, clear=True):
            self.assertRaises(JiraException, jira_client.report, 'stage_finished', mf, get_stage('BUILD'))



if __name__ == '__main__':
    unittest.main()
