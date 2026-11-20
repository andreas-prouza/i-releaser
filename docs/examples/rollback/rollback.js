// Rollback button of custom_templates/deployment_status.html (attributes data-rollback, data-project, data-version).
//
// Copy to: webapp/static/custom/rollback.js
//
// A script file instead of JavaScript in the template: the Content-Security-Policy of the web app
// blocks inline scripts and onclick attributes (docs/features/web-ui-security-headers.md).
// It uses the helpers of the web app (docs/scripts.md#scripts-of-custom-templates):
//   post_json       POST with JSON; throws the message of the server if it answers with an error
//   confirm_action  one dialog, which waits for the server and shows its error
//
// The workflow is started with POST. With a login session (cookie) the web app rejects actions with GET (405).
import { post_json } from '../assets/js/app/api.js';
import { confirm_action } from '../assets/js/app/dialogs.js';


document.addEventListener('click', async (event) => {

    const button = event.target.closest('[data-rollback]');
    if (!button) {
        return;
    }

    const {project, version} = button.dataset;

    const data = await confirm_action({
        title: 'Roll back this deployment?',
        // text, not html: the values are shown as text
        text: `Starts the workflow rollback_deployment for ${project}, version ${version}.`,
        confirm: 'Roll back',
        cancel: 'Keep it',
        danger: true,
        // Custom data of the new deployment
        action: () => post_json('/api/start_workflow/rollback_deployment', {project, version}),
    });

    if (data) {
        // The new deployment of the rollback workflow
        location.href = `/show_details/${encodeURIComponent(data.meta_file.general.id)}`;
    }
});
