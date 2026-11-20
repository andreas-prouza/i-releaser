/*
 * The permissions page (templates/admin/permissions.html, docs/features/web-ui-permissions-page.md)
 *
 * Left the users and roles, right one table per user or role: rows General, the workflows and their stages,
 * columns the permissions. A checkbox exists only where the permission is checked on that level (state.levels).
 * Permissions from a role or a higher level are shown as given (grey), with where they come from.
 *
 * Each change is saved at once (POST /api/save_permissions with the version of the state): the server answers 409
 * if the permissions have changed meanwhile, or if no user would have `admin` afterwards. Names are data, never selectors.
 */
import { get_json, post_json } from '../app/api.js';
import { confirm_action, show_error } from '../app/dialogs.js';
import { element, on_action, on_change, read_json } from '../app/dom.js';


let state = read_json('permissions-state');
const current_user = read_json('permissions-current');
let selected = from_url() || first_entry();
let busy = false;

const list_users = document.getElementById('perm-users');
const list_roles = document.getElementById('perm-roles');
const detail = document.getElementById('perm-detail');
const save_state = document.querySelector('.ir-save-state');
const search = document.querySelector('[data-action="perm-search"]');



//------------------------------------------------------------------------------
// Selection
//------------------------------------------------------------------------------

function from_url() {
    const match = location.hash.match(/^#(user|role)=(.+)$/);
    if (!match) {
        return null;
    }
    const name = decodeURIComponent(match[2]);
    return state[`${match[1]}s`][name] ? {kind: match[1], name} : null;
}


function first_entry() {
    const users = Object.keys(state.users);
    return users.length ? {kind: 'user', name: users[0]} : null;
}


function select(kind, name) {
    selected = {kind, name};
    history.replaceState(null, '', `#${kind}=${encodeURIComponent(name)}`);
    render();
}



//------------------------------------------------------------------------------
// Rendering (DOM only: names are text)
//------------------------------------------------------------------------------

function render_list() {
    const text = search.value.trim().toLowerCase();
    for (const [kind, list] of [['user', list_users], ['role', list_roles]]) {
        list.replaceChildren(...Object.keys(state[`${kind}s`])
            .filter((name) => !text || name.toLowerCase().includes(text))
            .map((name) => {
                const button = element('button', name, {type: 'button', class: 'ir-perm-name', 'data-action': 'perm-select'});
                button.dataset.kind = kind;
                button.dataset.name = name;
                if (selected && selected.kind === kind && selected.name === name) {
                    button.setAttribute('aria-current', 'true');
                }
                const item = element('li');
                item.append(button);
                return item;
            }));
    }
}


function sources_text(sources) {
    return `From ${sources.join(', ')}`;
}


/** A cell of the table: own checkbox, or given from elsewhere (grey), or nothing (not checked on this level) */
function cell(entry, level, action, own, effective, where) {
    const td = element('td');
    if (!state.levels[level].includes(action)) {
        return td;
    }

    const checked = own.includes(action);
    const sources = (effective || {})[action];
    const input = element('input', '', {type: 'checkbox', class: 'form-check-input'});
    input.dataset.action = 'perm-toggle';
    input.dataset.level = level;
    input.dataset.perm = action;
    input.dataset.workflow = where.workflow || '';
    input.dataset.stage = where.stage || '';
    input.checked = checked;
    input.setAttribute('aria-label', `${action}${where.workflow ? ` for ${where.workflow}` : ''}${where.stage ? ` / ${where.stage}` : ''}`);

    if (!checked && sources) {
        input.checked = true;
        input.disabled = true;
        input.classList.add('ir-inherited');
        input.title = sources_text(sources);
        input.setAttribute('aria-label', `${input.getAttribute('aria-label')}: ${sources_text(sources)}`);
    } else if (sources) {
        input.title = `Also ${sources_text(sources).toLowerCase()}`;
    }

    td.append(input);
    return td;
}


function name_cell(text, depth, remove = null) {
    const th = element('th', '', {scope: 'row', class: `ir-perm-level-${depth}`});
    th.append(element('span', text));
    if (remove) {
        const button = element('button', '', {type: 'button', class: 'btn btn-sm btn-link ir-perm-remove', title: remove.label, 'aria-label': remove.label});
        button.dataset.action = remove.action;
        button.dataset.workflow = remove.workflow || '';
        button.dataset.stage = remove.stage || '';
        button.append(element('i', '', {class: 'bi bi-x-lg', 'aria-hidden': 'true'}));
        th.append(button);
    }
    return th;
}


/** Workflows of the table: own ones and those which only come from roles */
function workflow_rows(entry) {
    const own = entry.permissions.workflows;
    const rows = {};
    for (const [name, value] of Object.entries(own)) {
        rows[name.toLowerCase()] = {name, own: true, stages: Object.keys(value.stages || {})};
    }
    for (const [name, value] of Object.entries(entry.effective.workflows)) {
        const row = rows[name.toLowerCase()] ||= {name, own: false, stages: []};
        for (const stage of Object.keys(value.stages || {})) {
            if (!row.stages.some((s) => s.toLowerCase() === stage.toLowerCase())) {
                row.stages.push(stage);
            }
        }
    }
    return Object.values(rows);
}


function find_key(object, name) {
    return Object.keys(object || {}).find((key) => key.toLowerCase() === name.toLowerCase());
}


function render_table(entry) {

    const columns = state.levels.workflow;
    const table = element('table', '', {class: 'table table-sm ir-perm-table'});
    const head = element('tr');
    head.append(element('th', '', {scope: 'col'}));
    for (const action of columns) {
        const th = element('th', action, {scope: 'col'});
        if (state.not_checked.includes(action)) {
            th.append(element('small', 'not checked yet', {class: 'ir-reason d-block'}));
        }
        head.append(th);
    }
    const thead = element('thead');
    thead.append(head);
    const tbody = element('tbody');

    const general = element('tr');
    general.append(name_cell('General', 0));
    columns.forEach((action) => general.append(cell(entry, 'general', action, entry.permissions.general, entry.effective.general, {})));
    tbody.append(general);

    for (const row of workflow_rows(entry)) {
        const own_key = find_key(entry.permissions.workflows, row.name);
        const own = own_key ? entry.permissions.workflows[own_key] : {general: [], stages: {}};
        const effective_key = find_key(entry.effective.workflows, row.name);
        const effective = effective_key ? entry.effective.workflows[effective_key] : {general: {}, stages: {}};

        const tr = element('tr', '', {class: 'ir-perm-workflow'});
        tr.append(name_cell(row.name, 1, own_key ? {action: 'remove-workflow', workflow: own_key, label: `Remove ${row.name}`} : null));
        if (!own_key) {
            tr.firstChild.append(element('small', 'from a role', {class: 'ir-reason ms-2'}));
        }
        columns.forEach((action) => tr.append(cell(entry, 'workflow', action, own.general || [], effective.general, {workflow: own_key || row.name})));
        tbody.append(tr);

        for (const stage of row.stages) {
            const own_stage = find_key(own.stages, stage);
            const effective_stage = find_key(effective.stages, stage);
            const st = element('tr');
            st.append(name_cell(stage, 2, own_stage ? {action: 'remove-stage', workflow: own_key, stage: own_stage, label: `Remove ${stage}`} : null));
            columns.forEach((action) => st.append(cell(entry, 'stage', action, own_stage ? own.stages[own_stage] : [],
                effective_stage ? effective.stages[effective_stage] : null, {workflow: own_key || row.name, stage: own_stage || stage})));
            tbody.append(st);
        }

        // + stage: stages of the workflow which are not in the table yet
        const definition = state.workflows.find((wf) => wf.name.toLowerCase() === row.name.toLowerCase());
        const free = (definition?.stages || []).filter((stage) => !row.stages.some((s) => s.toLowerCase() === stage.toLowerCase()));
        if (free.length) {
            const add = element('tr', '', {class: 'ir-perm-add'});
            const td = element('td', '', {colspan: String(columns.length + 1)});
            td.append(add_control('add-stage', `Add a stage of ${row.name}`, free, own_key || row.name));
            add.append(td);
            tbody.append(add);
        }
    }

    table.append(thead, tbody);
    const wrapper = element('div', '', {class: 'table-responsive'});
    wrapper.append(table);

    const free_workflows = state.workflows.map((wf) => wf.name)
        .filter((name) => !workflow_rows(entry).some((row) => row.own && row.name.toLowerCase() === name.toLowerCase()));
    const fragment = document.createDocumentFragment();
    fragment.append(wrapper);
    if (free_workflows.length) {
        fragment.append(add_control('add-workflow', 'Add a workflow', free_workflows));
    }
    return fragment;
}


function add_control(action, label, options, workflow = '') {
    const box = element('div', '', {class: 'ir-perm-add-control'});
    const select = element('select', '', {class: 'form-select form-select-sm', 'aria-label': label});
    select.append(element('option', label, {value: ''}));
    options.forEach((option) => select.append(element('option', option, {value: option})));
    const button = element('button', 'Add', {type: 'button', class: 'btn btn-sm btn-outline-secondary'});
    button.dataset.action = action;
    button.dataset.workflow = workflow;
    box.append(select, button);
    return box;
}


function render_detail() {

    if (!selected) {
        detail.replaceChildren(element('p', 'No user yet. Add one with + beside Users.', {class: 'ir-reason'}));
        return;
    }

    const entry = state[`${selected.kind}s`][selected.name];
    const head = element('div', '', {class: 'ir-perm-head'});
    head.append(element('h2', selected.name));
    const remove = element('button', selected.kind === 'user' ? 'Delete user' : 'Delete role', {type: 'button', class: 'btn btn-sm btn-outline-danger'});
    remove.dataset.action = 'delete-entry';
    head.append(remove);
    const parts = [head];

    if (selected.kind === 'user') {
        const infos = element('div', '', {class: 'ir-perm-infos'});
        for (const [field, label] of [['description', 'Description'], ['mail', 'Mail']]) {
            const id = `perm-${field}`;
            const input = element('input', '', {id, type: field === 'mail' ? 'email' : 'text', class: 'form-control form-control-sm'});
            input.value = entry.detailed_infos[field] || '';
            input.dataset.action = 'perm-info';
            input.dataset.field = field;
            const box = element('div');
            box.append(element('label', label, {for: id, class: 'form-label'}), input);
            infos.append(box);
        }
        parts.push(infos);

        const roles = element('fieldset', '', {class: 'ir-perm-roles'});
        roles.append(element('legend', 'Roles'));
        if (!Object.keys(state.roles).length) {
            roles.append(element('span', 'No roles yet', {class: 'ir-reason'}));
        }
        for (const role of Object.keys(state.roles)) {
            const id = `perm-role-${Object.keys(state.roles).indexOf(role)}`;
            const box = element('div', '', {class: 'form-check form-check-inline'});
            const input = element('input', '', {id, type: 'checkbox', class: 'form-check-input'});
            input.checked = entry.roles.includes(role);
            input.dataset.action = 'perm-role';
            input.dataset.role = role;
            box.append(input, element('label', role, {for: id, class: 'form-check-label'}));
            roles.append(box);
        }
        parts.push(roles);
    } else {
        parts.push(element('p', entry.users.length ? `Users with this role: ${entry.users.join(', ')}` : 'No user has this role', {class: 'ir-reason'}));
    }

    // admin: only on the general level, a switch of its own
    const admin = element('div', '', {class: 'form-check form-switch ir-perm-admin'});
    const admin_input = element('input', '', {id: 'perm-admin', type: 'checkbox', role: 'switch', class: 'form-check-input'});
    admin_input.checked = entry.permissions.general.includes('admin');
    admin_input.dataset.action = 'perm-toggle';
    admin_input.dataset.level = 'general';
    admin_input.dataset.perm = 'admin';
    admin_input.dataset.workflow = '';
    admin_input.dataset.stage = '';
    admin.append(admin_input, element('label', 'admin: settings, permissions, logs', {for: 'perm-admin', class: 'form-check-label'}));
    const admin_from = entry.effective.general.admin;
    if (admin_from && !admin_input.checked) {
        admin.append(element('span', ` (${sources_text(admin_from).toLowerCase()})`, {class: 'ir-reason'}));
    }
    parts.push(admin, render_table(entry));

    detail.replaceChildren(...parts);
}


function render() {
    render_list();
    render_detail();
}



//------------------------------------------------------------------------------
// Saving
//------------------------------------------------------------------------------

function show_saved(text, error = false) {
    save_state.textContent = text;
    save_state.classList.toggle('error', error);
}


async function reload_state() {
    state = await get_json('/api/permissions');
    if (selected && !state[`${selected.kind}s`][selected.name]) {
        selected = first_entry();
    }
    render();
}


async function send(url, payload) {

    if (busy) {
        return false;
    }
    busy = true;
    detail.setAttribute('aria-busy', 'true');

    try {
        const result = await post_json(url, {...payload, version: state.version});
        await reload_state();
        show_saved(`Saved ${new Date().toLocaleTimeString()}`);
        return result;
    } catch (error) {
        render();   // the state of the page before the change
        if (error.status === 401) {
            return false;
        }
        show_saved('Not saved', true);
        if (error.status === 409 && error.message.includes('changed meanwhile')) {
            const load = await confirm_action({title: 'Changed meanwhile', text: error.message, confirm: 'Load the current state', icon: 'warning'});
            if (load) {
                await reload_state();
            }
        } else {
            show_error(error, 'Not saved');
        }
        return false;
    } finally {
        busy = false;
        detail.removeAttribute('aria-busy');
    }
}


function save_selected(change) {
    const kind = selected.kind;
    const entry = structuredClone(state[`${kind}s`][selected.name]);
    change(entry);
    const data = {permissions: entry.permissions};
    if (kind === 'user') {
        data.roles = entry.roles;
        data.detailed_infos = entry.detailed_infos;
    }
    return send('/api/save_permissions', {[`${kind}_permissions`]: {[selected.name]: data}});
}


function level_list(permissions, level, workflow, stage) {
    if (level === 'general') {
        return permissions.general;
    }
    const wf = permissions.workflows[workflow] ||= {general: [], stages: {}};
    wf.general ||= [];
    wf.stages ||= {};
    if (level === 'workflow') {
        return wf.general;
    }
    return wf.stages[stage] ||= [];
}



//------------------------------------------------------------------------------
// Actions
//------------------------------------------------------------------------------

on_action('perm-select', (button) => select(button.dataset.kind, button.dataset.name));

search.addEventListener('input', render_list);


on_change('perm-toggle', async (input) => {

    const {level, perm, workflow, stage} = input.dataset;
    const add = input.checked;

    // Removing the own admin permission asks first
    if (perm === 'admin' && !add && selected.kind === 'user' && selected.name === current_user) {
        const sure = await confirm_action({title: 'Remove your own admin permission?', text: "You can't open the settings and this page any more afterwards, unless a role gives it to you.",
                                           confirm: 'Remove admin', danger: true});
        if (!sure) {
            input.checked = true;
            return;
        }
    }

    await save_selected((entry) => {
        const list = level_list(entry.permissions, level, workflow, stage);
        const index = list.indexOf(perm);
        if (add && index < 0) {
            list.push(perm);
        } else if (!add && index >= 0) {
            list.splice(index, 1);
        }
    });
});


on_change('perm-role', (input) => save_selected((entry) => {
    entry.roles = input.checked ? [...entry.roles, input.dataset.role] : entry.roles.filter((role) => role !== input.dataset.role);
}));


on_change('perm-info', (input) => save_selected((entry) => {
    entry.detailed_infos[input.dataset.field] = input.value.trim();
}));


on_action('add-workflow', (button) => {
    const workflow = button.parentElement.querySelector('select').value;
    if (workflow) {
        save_selected((entry) => {
            entry.permissions.workflows[workflow] ||= {general: [], stages: {}};
        });
    }
});


on_action('add-stage', (button) => {
    const stage = button.parentElement.querySelector('select').value;
    const workflow = button.dataset.workflow;
    if (stage) {
        save_selected((entry) => {
            level_list(entry.permissions, 'stage', find_key(entry.permissions.workflows, workflow) || workflow, stage);
        });
    }
});


on_action('remove-workflow', async (button) => {
    const workflow = button.dataset.workflow;
    const sure = await confirm_action({title: `Remove ${workflow}?`, text: `The permissions of ${selected.name} for ${workflow} and its stages are removed.`, confirm: 'Remove', danger: true});
    if (sure) {
        save_selected((entry) => {
            delete entry.permissions.workflows[workflow];
        });
    }
});


on_action('remove-stage', (button) => save_selected((entry) => {
    delete entry.permissions.workflows[button.dataset.workflow].stages[button.dataset.stage];
}));


on_action('delete-entry', async () => {
    const {kind, name} = selected;
    const users = kind === 'role' ? state.roles[name].users.length : 0;
    const sure = await confirm_action({
        title: `Delete the ${kind} ${name}?`,
        text: kind === 'role' ? `${users} user${users === 1 ? ' has' : 's have'} this role.` : 'The user can\'t log in to i-Releaser any more.',
        confirm: `Delete ${kind}`, danger: true,
    });
    if (sure) {
        send('/api/save_permissions', {[`deleted_${kind}s`]: [name]});
    }
});


async function add_entry(kind) {
    const result = await Swal.fire({
        title: kind === 'user' ? 'Add a user' : 'Add a role',
        input: 'text',
        inputLabel: kind === 'user' ? 'The user profile on IBM i' : 'Name of the role',
        showCancelButton: true,
        confirmButtonText: 'Add',
        buttonsStyling: false,
        reverseButtons: true,
        customClass: {confirmButton: 'btn btn-primary', cancelButton: 'btn btn-outline-secondary', actions: 'ir-dialog-actions'},
    });
    if (!result.isConfirmed) {
        return;
    }
    const added = await send('/api/add_permission', {type: kind, name: result.value, general: []});
    if (added) {
        select(kind, added.name);
    }
}

on_action('add-user', () => add_entry('user'));
on_action('add-role', () => add_entry('role'));


window.addEventListener('hashchange', () => {
    selected = from_url() || selected;
    render();
});

render();
