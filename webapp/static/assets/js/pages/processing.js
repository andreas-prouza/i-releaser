/*
 * Settings, processing of stages (templates/admin/processing.html, docs/processing-service.md)
 *
 * Mode, processing service and auto start. The result of an action is a toast, the output of the service script a
 * dialog. Afterwards the part of the page is loaded again (GET /settings/processing), the page is not reloaded.
 */
import { get_html, post_json } from '../app/api.js';
import { confirm_action, show_error, toast } from '../app/dialogs.js';
import { escape_html, element, on_action, on_change, read_json } from '../app/dom.js';
import { local_time_text } from '../app/time.js';


function pill(view) {
    return `<span class="ir-pill k-${escape_html(view.kind)}"><i class="bi bi-${escape_html(view.icon)}" aria-hidden="true"></i>${escape_html(view.text)}</span>`;
}


function init_jobs() {
    const $table = $('#jobs');
    if (!$table.length) {
        return;
    }
    $table.bootstrapTable({
        data: read_json('jobs-data') || [],
        filterControl: true,
        pagination: true,
        pageSize: 10,
        sortName: 'id',
        sortOrder: 'desc',
        paginationHAlign: 'left',
        paginationDetailHAlign: 'left',
        columns: [
            {field: 'id', title: 'Job', sortable: true},
            {field: 'deployment', title: 'Deployment', sortable: true, filterControl: 'select',
             formatter: (value, row) => `<a href="/show_details/${encodeURIComponent(row.meta_file_id)}">${escape_html(value)}</a>`},
            {field: 'stage', title: 'Stage', sortable: true, filterControl: 'select'},
            {field: 'user', title: 'User', sortable: true, filterControl: 'select'},
            {field: 'status', title: 'Status', sortable: true, filterControl: 'select', formatter: (value, row) => pill(row.status_view)},
            {field: 'queued', title: 'Queued', sortable: true},
            {field: 'scheduled', title: 'Scheduled for', sortable: true,
             formatter: (value) => value ? `<time datetime="${escape_html(value)}" title="${escape_html(value)}">${escape_html(local_time_text(value) || value)}</time>` : ''},
            {field: 'started', title: 'Started', sortable: true},
            {field: 'ended', title: 'Ended', sortable: true},
            {field: 'duration', title: 'Duration'},
            {field: 'process', title: 'Process'},
            {field: 'error', title: 'Error'},
        ],
    });
}


async function refresh() {
    try {
        const html = await get_html('/settings/processing');
        // A part of a page of the server (rule 4 of docs/features/web-ui-scripts.md#rules)
        const next = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-part="processing"]');
        document.querySelector('[data-part="processing"]').replaceWith(document.importNode(next, true));
        init_jobs();
    } catch (error) {
        if (error.status !== 401) {
            show_error(error);
        }
    }
}


function show_output(title, text, ok = true) {
    const pre = element('pre', text || 'No output', {class: 'ir-log wrap text-start'});
    return Swal.fire({title, html: pre, icon: ok ? 'success' : 'error', confirmButtonText: 'Close', buttonsStyling: false,
                      customClass: {confirmButton: 'btn btn-primary', actions: 'ir-dialog-actions'}});
}


async function control_service(command) {
    Swal.fire({title: `Processing service: ${command} …`, allowOutsideClick: false, didOpen: () => Swal.showLoading()});
    try {
        const data = await post_json(`/api/processing_service/${encodeURIComponent(command)}`);
        await show_output(`Processing service: ${command}`, data.output);
    } catch (error) {
        Swal.close();
        if (error.status !== 401) {
            await show_output(`Processing service: ${command}`, error.message, false);
        }
    }
    await refresh();
}


on_action('set-processing-mode', async () => {

    const mode = document.getElementById('processing-mode').value;
    let data;
    try {
        data = await post_json(`/api/set_processing_mode/${encodeURIComponent(mode)}`);
    } catch (error) {
        if (error.status !== 401) {
            show_error(error);
        }
        return;
    }

    if (mode === 'service' && !data.service_running) {
        const start = await confirm_action({title: 'The processing service is not running', text: 'Stages stay in the queue until the service has been started.',
                                            confirm: 'Start it', cancel: 'Later', icon: 'warning'});
        if (start) {
            await control_service('start');
            return;
        }
    } else {
        toast(`Next stages run in mode ${mode}`);
    }
    await refresh();
});


on_action('processing-service', (button) => control_service(button.dataset.command));


on_change('service-auto-start', async (input) => {
    try {
        await post_json(`/api/set_service_auto_start/${input.checked}`);
        toast(input.checked ? 'The service starts automatically' : 'Auto start is off');
    } catch (error) {
        input.checked = !input.checked;
        if (error.status !== 401) {
            show_error(error);
        }
    }
    // Paused, or only active in mode service
    await refresh();
});


init_jobs();
