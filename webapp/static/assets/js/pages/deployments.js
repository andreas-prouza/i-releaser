/*
 * The deployments of a project (templates/overview/list-deployments.html, docs/features/web-ui-lists.md#deployments)
 *
 * The rows come from the JSON block #deployments-data; the whole list is loaded at once (fewer than 2,000 per project).
 * A click on a row opens the deployment. `Open | All`, filters for status and workflow, a search, sorting, paging.
 */
import { escape_html, on_change, read_json } from '../app/dom.js';


const rows = read_json('deployments-data') || [];
const $table = $('#deployments');


// bootstrap-table formatters return HTML: only escaped values go into it
function pill(view) {
    if (!view) {
        return '–';
    }
    return `<span class="ir-pill k-${escape_html(view.kind)}"><i class="bi bi-${escape_html(view.icon)}" aria-hidden="true"></i>${escape_html(view.text)}</span>`;
}


function version_formatter(value, row) {
    return `<a href="/show_details/${encodeURIComponent(row.id)}">Version ${escape_html(value)}</a>`;
}


function stage_formatter(value, row) {
    return row.stage_view ? `${escape_html(value)} <span class="ir-reason">· ${escape_html(row.stage_view.text)}</span>` : '–';
}


if ($table.length) {

    $table.bootstrapTable({
        data: rows,
        uniqueId: 'id',
        toolbar: '#deployments-toolbar',
        search: true,
        searchAlign: 'right',
        showSearchClearButton: true,
        showColumns: true,
        filterControl: true,
        pagination: true,
        pageSize: 25,
        pageList: [10, 25, 50, 100, 'all'],
        sortName: 'version',
        sortOrder: 'desc',
        paginationHAlign: 'left',
        paginationDetailHAlign: 'left',
        buttonsAlign: 'right',
        rowStyle: () => ({classes: 'ir-clickable'}),
        columns: [
            {field: 'version', title: 'Version', sortable: true, formatter: version_formatter, searchable: true},
            {field: 'status', title: 'Status', sortable: true, filterControl: 'select', formatter: (value, row) => pill(row.status_view)},
            {field: 'workflow', title: 'Workflow', sortable: true, filterControl: 'select'},
            {field: 'stage', title: 'Stage', sortable: true, formatter: stage_formatter},
            {field: 'created', title: 'Created', sortable: true},
            {field: 'updated', title: 'Last update', sortable: true},
            {field: 'id', title: 'Id', sortable: true, visible: false},
        ],
        // The whole row opens the deployment (the link in it as well)
        onClickRow: (row, element, field) => {
            if (!window.getSelection().toString()) {
                location.href = `/show_details/${encodeURIComponent(row.id)}`;
            }
        },
    });

    on_change('which-deployments', (input) => {
        $table.bootstrapTable('filterBy', input.value === 'open' ? {open: [true]} : {});
    });
}
