/*
 * The objects of all deployments (templates/overview/list-objects.html, docs/features/web-ui-lists.md#objects)
 *
 * The rows come page by page from GET /api/deploy_objects (search, filters, sort, offset, limit), so every object can be
 * found. `History` opens the deployments of an object, rendered by the server (GET /list-objects/history).
 */
import { get_html, get_json } from '../app/api.js';
import { show_error } from '../app/dialogs.js';
import { escape_html, on_action, read_json } from '../app/dom.js';


const filters = read_json('object-filters') || {};
const $table = $('#objects');


// The values of a filter select, for the server side paging (bootstrap-table can't know them from one page)
function filter_data(values) {
    return 'json:' + JSON.stringify(Object.fromEntries(values.map((value) => [value, value])));
}


function history_formatter(value, row) {
    const data = ['project', 'prod_lib', 'name', 'type', 'attribute']
        .map((key) => `data-${key.replace('_', '-')}="${escape_html(row[key])}"`).join(' ');
    return `<button type="button" class="btn btn-sm btn-outline-secondary" data-action="object-history" ${data}>History</button>`;
}


$table.bootstrapTable({
    sidePagination: 'server',
    // The one fetch of the pages: errors as messages, an ended session as such
    ajax: (request) => {
        get_json(`/api/deploy_objects?${new URLSearchParams(request.data)}`)
            .then((data) => request.success(data))
            .catch((error) => {
                request.error(error);
                if (error.status !== 401) {
                    show_error(error);
                }
            });
    },
    search: true,
    searchAlign: 'right',
    showSearchClearButton: true,
    showColumns: true,
    filterControl: true,
    pagination: true,
    pageSize: 25,
    pageList: [10, 25, 50, 100],
    sortName: 'last_deployment',
    sortOrder: 'desc',
    paginationHAlign: 'left',
    paginationDetailHAlign: 'left',
    buttonsAlign: 'right',
    columns: [
        {field: 'project', title: 'Project', sortable: true, filterControl: 'select', filterData: filter_data(filters.project || [])},
        {field: 'prod_lib', title: 'Production library', sortable: true, filterControl: 'input'},
        {field: 'name', title: 'Name', sortable: true, filterControl: 'input'},
        {field: 'type', title: 'Type', sortable: true, filterControl: 'select', filterData: filter_data(filters.type || [])},
        {field: 'attribute', title: 'Attribute', sortable: true, filterControl: 'select', filterData: filter_data(filters.attribute || [])},
        {field: 'last_deployment', title: 'Last deployment', sortable: true},
        {field: 'deployments', title: 'Deployments', sortable: true, align: 'right'},
        {field: 'history', title: 'History', formatter: history_formatter},
    ],
});


const dialog = document.getElementById('object-history');

on_action('object-history', async (button) => {

    const params = new URLSearchParams({
        project: button.dataset.project, prod_lib: button.dataset.prodLib, name: button.dataset.name,
        type: button.dataset.type, attribute: button.dataset.attribute,
    });

    try {
        const html = await get_html(`/list-objects/history?${params}`);
        // A part of a page of the server (rule 4 of docs/features/web-ui-scripts.md#rules)
        const part = new DOMParser().parseFromString(html, 'text/html').querySelector('.ir-object-history');
        document.getElementById('object-history-title').textContent = part.dataset.title;
        document.getElementById('object-history-body').replaceChildren(document.importNode(part, true));
        bootstrap.Modal.getOrCreateInstance(dialog).show();
    } catch (error) {
        if (error.status !== 401) {
            show_error(error);
        }
    }
});
