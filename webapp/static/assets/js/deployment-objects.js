// Table "Objects to deploy" of the deployment page (docs/bugfixes/deployment-objects-table.md)
//
// The rows come from the JSON block #deployment-objects. Objects are identified by these values,
// never by the HTML of a cell. Which switch can be used is decided by the server (`can_change`).

const STATUS_CLASSES = {
    'finished': 'btn-success',
    'failed': 'btn-danger',
    'canceled': 'btn-danger',
    'new': 'btn-info',
    'ready': 'btn-primary',
    'in process': 'btn-secondary',
};

const data_block = document.getElementById('deployment-objects');


async function post_json(url, body) {

    const response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify(body),
    });

    let data = {};
    try {
        data = await response.json();
    } catch (error) {
        // An empty or broken body: the status tells enough
    }

    if (!response.ok) {
        throw new Error(data.message || `The server answered with status ${response.status}`);
    }
    return data;
}


function show_error(message) {
    Swal.fire({icon: 'error', title: 'Error', text: message});
}


function show_toast(message) {
    Swal.fire({toast: true, position: 'top-end', icon: 'success', title: message, showConfirmButton: false, timer: 2500});
}


function plural(count, word) {
    return `${count} ${word}${count === 1 ? '' : 's'}`;
}


// Only booleans go into this HTML. The values of the other columns are escaped by bootstrap-table (`escape`).
function ready_formatter(value, row) {
    return '<div class="form-check form-switch m-0">'
        + `<input class="form-check-input obj-ready" type="checkbox" role="switch" aria-label="Ready"${row.ready ? ' checked' : ''}${row.can_change ? '' : ' disabled'}>`
        + '</div>';
}


// `value` is already escaped
function status_formatter(value) {
    return `<span class="btn btn-sm ${STATUS_CLASSES[value] || 'btn-secondary'} pe-none">${value}</span>`;
}


function init(page) {

    const $table = $('#object_list');
    const toolbar = document.getElementById('object_toolbar');


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
            show_error(error.message);
        } finally {
            checkbox.disabled = !row.can_change;
        }
    }


    // All objects which match the filters, on all pages
    async function set_all_ready(ready) {

        const rows = $table.bootstrapTable('getData').filter((row) => row.can_change && row.ready !== ready);

        if (rows.length === 0) {
            show_toast(ready ? 'All of these objects are ready already' : 'None of these objects is ready');
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
            show_toast(message);
        } catch (error) {
            show_error(error.message);
        } finally {
            buttons.forEach((button) => button.disabled = false);
        }
    }


    $table.bootstrapTable({
        data: page.objects,
        escape: true,
        uniqueId: 'id',
        toolbar: toolbar ? '#object_toolbar' : undefined,
        filterControl: true,
        showSearchClearButton: true,
        showColumns: true,
        pagination: true,
        pageList: [5, 10, 20, 50, 100, 'all'],
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
            {field: 'prod_lib', title: 'Prod Lib', sortable: true, filterControl: 'input'},
            {field: 'lib', title: 'Target Lib', sortable: true, filterControl: 'input'},
            {field: 'name', title: 'Name', sortable: true, filterControl: 'input'},
            {field: 'type', title: 'Type', sortable: true, filterControl: 'select'},
            {field: 'attribute', title: 'Attribute', sortable: true, filterControl: 'select'},
            {field: 'source_only', title: 'Source Only', sortable: true, filterControl: 'select'},
            {field: 'status', title: 'Status', sortable: true, filterControl: 'select', formatter: status_formatter},
        ],
    });

    if (toolbar) {
        toolbar.querySelectorAll('[data-objects-ready]').forEach((button) => {
            button.addEventListener('click', () => set_all_ready(button.dataset.objectsReady === 'true'));
        });
    }
}


if (data_block) {
    init(JSON.parse(data_block.textContent));
}
