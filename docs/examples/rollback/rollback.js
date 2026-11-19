// Rollback button of custom_templates/deployment_status.html (attributes data-rollback, data-project, data-version).
//
// Copy to: webapp/static/custom/rollback.js
//
// A script file instead of JavaScript in the template: the Content-Security-Policy of the web app
// blocks inline scripts and onclick attributes (docs/features/web-ui-security-headers.md).
// It only uses what every page of the web app has: Swal (SweetAlert2) and fetch.
//
// The workflow is started with POST. With a login session (cookie) the web app rejects actions with GET (405).


async function start_rollback(project, version) {

    const response = await fetch('/api/start_workflow/rollback_deployment', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        // Custom data of the new deployment
        body: JSON.stringify({project: project, version: version}),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.message || `The server answered with status ${response.status}`);
    }

    return data;
}



document.addEventListener('click', async (event) => {

    const button = event.target.closest('[data-rollback]');
    if (!button) {
        return;
    }

    const project = button.dataset.project;
    const version = button.dataset.version;

    const result = await Swal.fire({
        icon: 'warning',
        title: 'Roll back this deployment?',
        // text, not html: the values are shown as text
        text: `Starts the workflow rollback_deployment for ${project}, version ${version}.`,
        showCancelButton: true,
        confirmButtonText: 'Roll back',
        cancelButtonText: 'Keep it',
        reverseButtons: true,
        showLoaderOnConfirm: true,
        allowOutsideClick: () => !Swal.isLoading(),
        // The dialog stays open until the server has answered, and shows its error
        preConfirm: () => start_rollback(project, version).catch((error) => {
            Swal.showValidationMessage(error.message);
            return false;
        }),
    });

    if (result.isConfirmed) {
        // The new deployment of the rollback workflow
        location.href = `/show_details/${encodeURIComponent(result.value.meta_file.general.id)}`;
    }
});
