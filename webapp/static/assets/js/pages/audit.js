/*
 * Settings, audit (templates/admin/audit.html, docs/features/audit-log.md)
 *
 * One table of the security events and the actions on deployments, with filters. Times in the time zone of the browser.
 */
import { escape_html, read_json } from '../app/dom.js';
import { local_time_text } from '../app/time.js';


const $table = $('#audit');

if ($table.length) {
    $table.bootstrapTable({
        data: read_json('audit-data') || [],
        filterControl: true,
        pagination: true,
        pageSize: 25,
        sortName: 'time',
        sortOrder: 'desc',
        paginationHAlign: 'left',
        paginationDetailHAlign: 'left',
        columns: [
            {field: 'time', title: 'Time', sortable: true,
             formatter: (value) => `<time datetime="${escape_html(value)}" title="${escape_html(value)}">${escape_html(local_time_text(value) || value)}</time>`},
            {field: 'user', title: 'User', sortable: true, filterControl: 'select'},
            {field: 'event', title: 'Event', sortable: true, filterControl: 'select'},
            {field: 'object', title: 'Object', sortable: true, filterControl: 'input',
             formatter: (value, row) => row.meta_file_id ? `<a href="/show_details/${encodeURIComponent(row.meta_file_id)}">${escape_html(value)}</a>` : escape_html(value)},
            {field: 'result', title: 'Result', sortable: true, filterControl: 'select'},
            {field: 'client', title: 'Client', filterControl: 'input'},
            {field: 'details', title: 'Details', filterControl: 'input', formatter: (value) => `<span class="ir-mono">${escape_html(value)}</span>`},
        ],
    });
}
