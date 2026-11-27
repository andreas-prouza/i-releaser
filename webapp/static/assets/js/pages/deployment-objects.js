/*
 * Table "Objects" of the deployment page (docs/bugfixes/deployment-objects-table.md, docs/features/web-ui-deployment-page.md#objects)
 *
 * The rows come from the JSON block #deployment-objects (and GET /api/deployment_objects/{id}). Objects are identified
 * by these values, never by the HTML of a cell. Which switch can be used is decided by the server (`can_change`).
 */
import { get_json, post_json } from '../app/api.js';
import { show_error, toast } from '../app/dialogs.js';
import { escape_html, read_json } from '../app/dom.js';


function plural(count, word) {
    return `${count} ${word}${count === 1 ? '' : 's'}`;
}


// bootstrap-table formatters return HTML: only booleans and escaped values go into it
function ready_formatter(value, row) {
    return '<div class="form-check form-switch m-0">'
        + `<input class="form-check-input obj-ready" type="checkbox" role="switch" aria-label="Ready"${row.ready ? ' checked' : ''}${row.can_change ? '' : ' disabled'}>`
        + '</div>';
}


// The view of the status comes from the server (web_modules/status_view.py)
function status_formatter(value, row) {
    const view = row.status_view || {kind: 'neutral', icon: 'dot', text: row.status};
    return `<span class="ir-pill k-${escape_html(view.kind)}"><i class="bi bi-${escape_html(view.icon)}" aria-hidden="true"></i>${escape_html(view.text)}</span>`;
}


function source_only_formatter(value) {
    return value === 'yes' ? '<i class="bi bi-check-lg" aria-label="yes"></i>' : '';
}


export function init_objects() {

    const page = read_json('deployment-objects');
    if (!page) {
        return null;
    }

    const $table = $('#object_list');
    const toolbar = document.getElementById('object_toolbar');
    const table_card = document.querySelector('[data-objects-table]');
    const empty_card = document.querySelector('[data-objects-empty]');


    // A deployment can get its objects after the page was loaded (e.g. by a SCRIPT step): the table is set up
    // without rows and shown with the first object (docs/bugfixes/objects-added-later-not-shown.md)
    function show_table(count) {
        const was_hidden = table_card.hidden;
        table_card.hidden = count === 0;
        empty_card.hidden = count > 0;
        if (was_hidden && count > 0) {
            // Set up while hidden: the header gets its width now
            $table.bootstrapTable('resetView');
        }
    }


    // The rows of the current page show the values of their data (after a change of several rows)
    function sync_switches() {
        const rows = $table.bootstrapTable('getData');
        $table[0].querySelectorAll('tbody tr[data-index]').forEach((tr) => {
            const row = rows[Number(tr.dataset.index)];
            const checkbox = tr.querySelector('.obj-ready');
            if (row && checkbox) {
                checkbox.checked = row.ready;
                checkbox.disabled = !row.can_change;
            }
        });
    }


    async function set_ready(checkbox, row) {

        const ready = checkbox.checked;
        checkbox.disabled = true;

        try {
            await post_json(`/api/set_source_ready_4_deployment/${page.meta_file_id}`, {lib: row.lib, name: row.name, type: row.type, checked: ready});
            row.ready = ready;
        } catch (error) {
            checkbox.checked = row.ready;
            show_error(error);
        } finally {
            checkbox.disabled = !row.can_change;
        }
    }


    // All objects which match the filters, on all pages
    async function set_all_ready(ready) {

        const rows = $table.bootstrapTable('getData').filter((row) => row.can_change && row.ready !== ready);

        if (rows.length === 0) {
            toast(ready ? 'All of these objects are ready already' : 'None of these objects is ready', 'info');
            return;
        }

        const buttons = toolbar.querySelectorAll('button');
        buttons.forEach((button) => button.disabled = true);

        try {
            const result = await post_json(`/api/set_objects_ready/${page.meta_file_id}`, {
                ready: ready,
                objects: rows.map((row) => ({lib: row.lib, name: row.name, type: row.type})),
            });

            // Finished meanwhile: can't be changed any more
            const finished = new Set(result.finished.map((o) => JSON.stringify([o.lib, o.name, o.type])));

            rows.forEach((row) => {
                if (finished.has(JSON.stringify([row.lib, row.name, row.type]))) {
                    row.can_change = false;
                    row.status = 'finished';
                } else {
                    row.ready = ready;
                }
            });

            sync_switches();

            let message = `${plural(rows.length - finished.size, 'object')} ${ready ? 'included' : 'excluded'}`;
            if (finished.size > 0) {
                message += `, ${plural(finished.size, 'finished object')} unchanged`;
            }
            toast(message);
        } catch (error) {
            show_error(error);
        } finally {
            buttons.forEach((button) => button.disabled = false);
        }
    }


    $table.bootstrapTable({
        data: page.objects,
        uniqueId: 'id',
        toolbar: toolbar ? '#object_toolbar' : undefined,
        filterControl: true,
        showSearchClearButton: true,
        showColumns: true,
        pagination: true,
        pageList: [10, 25, 50, 100, 'all'],
        pageSize: 10,
        sortName: 'level',
        sortOrder: 'asc',
        sortStable: true,
        paginationHAlign: 'left',
        paginationDetailHAlign: 'left',
        buttonsAlign: 'left',
        searchAlign: 'left',
        columns: [
            {field: 'ready', title: 'Ready', formatter: ready_formatter, events: {'change .obj-ready': (event, value, row) => set_ready(event.target, row)}},
            {field: 'level', title: 'Level', sortable: true, filterControl: 'select'},
            {field: 'prod_lib', title: 'Production library', sortable: true, filterControl: 'input'},
            {field: 'lib', title: 'Target library', sortable: true, filterControl: 'input'},
            {field: 'name', title: 'Name', sortable: true, filterControl: 'input'},
            {field: 'type', title: 'Type', sortable: true, filterControl: 'select'},
            {field: 'attribute', title: 'Attribute', sortable: true, filterControl: 'select'},
            {field: 'source_only', title: 'Source only', sortable: true, filterControl: 'select', formatter: source_only_formatter},
            {field: 'status', title: 'Status', sortable: true, filterControl: 'select', formatter: status_formatter},
        ],
    });

    if (toolbar) {
        toolbar.querySelectorAll('[data-objects-ready]').forEach((button) => {
            button.addEventListener('click', () => set_all_ready(button.dataset.objectsReady === 'true'));
        });
    }

    // New rows without losing sorting, filters and the page (live updates, docs/features/web-ui-live-updates.md).
    // Returns the number of objects.
    return {
        refresh: async () => {
            const data = await get_json(`/api/deployment_objects/${page.meta_file_id}`);
            const page_number = $table.bootstrapTable('getOptions').pageNumber;
            $table.bootstrapTable('load', data.objects);
            $table.bootstrapTable('selectPage', Math.min(page_number, $table.bootstrapTable('getOptions').totalPages || 1));
            show_table(data.objects.length);
            return data.objects.length;
        },
    };
}
