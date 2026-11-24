/*
 * The deployment page (templates/overview/show-deployment.html, docs/features/web-ui-deployment-page.md)
 *
 * - Stage flow: a click selects a stage, its steps are loaded into the panel below (#stage=<id> in the URL).
 * - Steps panel: closed by default, opened by itself only for a problem (scrolled to the latest error);
 *   filter, "only failed and running", one step opens its details.
 * - Actions: run, run at a time (scheduled run), reset, cancel, remove from queue, custom data, check error. One dialog, then a toast.
 * - Logs: one dialog over the page; the steps stay as they are behind it.
 * - Live updates (docs/features/web-ui-live-updates.md): the parts of the page which changed are replaced in place,
 *   the page is never loaded again. Filters, the page of the objects table, open steps and dialogs stay.
 */
import { get_html, get_json, post_json } from '../app/api.js';
import { choose, confirm_action, show_error, toast } from '../app/dialogs.js';
import { on_action, on_change, read_json } from '../app/dom.js';
import { local_input_to_iso, local_time_text, to_local_input, zone_name } from '../app/time.js';
import { init_objects } from './deployment-objects.js';


const page = read_json('deployment-page');
const meta_file_id = page.meta_file_id;

const objects = init_objects();
highlight(document);



function highlight(root) {
    if (window.Prism) {
        root.querySelectorAll('code[class*="language-"]').forEach((block) => Prism.highlightElement(block));
    }
}



//------------------------------------------------------------------------------
// Steps panel
//------------------------------------------------------------------------------

function panel() {
    return document.getElementById('stage-steps');
}


function is_open(steps = panel()) {
    return steps !== null && !steps.querySelector('.ir-steps-body').hidden;
}


function set_open(open, steps = panel()) {
    if (!steps) {
        return;
    }
    steps.querySelector('.ir-steps-body').hidden = !open;
    steps.classList.toggle('open', open);
    steps.querySelector('[data-action="toggle-steps"]').setAttribute('aria-expanded', String(open));
}


function set_step_open(step, open) {
    step.querySelector(':scope > .ir-step-row .ir-step-toggle').setAttribute('aria-expanded', String(open));
    step.querySelector(':scope > .ir-step-detail').hidden = !open;
}


function scroll_to_step(step_id, steps = panel()) {
    const step = steps?.querySelector(`.ir-step[data-step-id="${CSS.escape(String(step_id))}"]`);
    if (!step) {
        return;
    }
    // Folded rows around it open
    for (let parent = step.parentElement; parent && parent !== steps; parent = parent.parentElement) {
        if (parent.tagName === 'DETAILS') {
            parent.open = true;
        }
    }
    set_step_open(step, true);
    const list = steps.querySelector('.ir-steps-body');
    list.scrollTop = step.offsetTop - list.offsetTop - 8;
    step.scrollIntoView({block: 'nearest'});
}


function apply_filter(steps = panel()) {
    if (!steps) {
        return;
    }
    const text = (steps.querySelector('[data-action="filter-steps"]')?.value || '').trim().toLowerCase();
    const only_problems = steps.querySelector('[data-action="only-problems"]')?.checked || false;
    const filtering = text !== '' || only_problems;
    let shown = 0;

    steps.querySelectorAll('.ir-step').forEach((step) => {
        const matches = (!text || step.dataset.search.includes(text))
            && (!only_problems || ['failed', 'in process'].includes(step.dataset.status));
        step.classList.toggle('ir-filtered', filtering && !matches);
        if (matches) {
            shown++;
        }
    });

    // While filtering, folded rows and groups show what matches inside them
    steps.querySelectorAll('.ir-step-fold, .ir-step-group').forEach((box) => {
        const visible = box.querySelectorAll('.ir-step:not(.ir-filtered)').length > 0;
        box.classList.toggle('ir-filtered', filtering && !visible);
        if (box.tagName === 'DETAILS' && filtering && visible) {
            box.open = true;
        }
    });

    steps.classList.toggle('filtering', filtering);
    const nothing = steps.querySelector('.ir-steps-body > .ir-steps-nothing');
    if (nothing && steps.querySelector('.ir-step-list')) {
        nothing.hidden = !filtering || shown > 0;
    }
}


function select_node(stage_id) {
    document.querySelectorAll('.ir-flow-node').forEach((node) => {
        const selected = node.dataset.stageId === String(stage_id);
        node.classList.toggle('selected', selected);
        node.setAttribute('aria-pressed', String(selected));
    });
}


/** State of the panel which a refresh of its stage keeps */
function panel_state(steps = panel()) {
    return {
        open: is_open(steps),
        filter: steps?.querySelector('[data-action="filter-steps"]')?.value || '',
        only_problems: steps?.querySelector('[data-action="only-problems"]')?.checked || false,
        open_steps: [...(steps?.querySelectorAll('.ir-step-toggle[aria-expanded="true"]') || [])].map((b) => b.closest('.ir-step').dataset.stepId),
        folds: [...(steps?.querySelectorAll('details[open]') || [])].map((d) => d.querySelector('.ir-step')?.dataset.stepId).filter(Boolean),
        scroll: steps?.querySelector('.ir-steps-body')?.scrollTop || 0,
    };
}


function restore_state(steps, state) {
    set_open(state.open, steps);
    const filter = steps.querySelector('[data-action="filter-steps"]');
    if (filter) {
        filter.value = state.filter;
    }
    const only = steps.querySelector('[data-action="only-problems"]');
    if (only) {
        only.checked = state.only_problems;
    }
    for (const id of state.folds) {
        const step = steps.querySelector(`.ir-step[data-step-id="${CSS.escape(id)}"]`);
        const fold = step?.closest('details');
        if (fold) {
            fold.open = true;
        }
    }
    for (const id of state.open_steps) {
        const step = steps.querySelector(`.ir-step[data-step-id="${CSS.escape(id)}"]`);
        if (step) {
            set_step_open(step, true);
        }
    }
    apply_filter(steps);
    steps.querySelector('.ir-steps-body').scrollTop = state.scroll;
}


/** Loads the steps of a stage into the panel. keep: the state of the panel (a refresh of the same stage). */
async function load_steps(stage_id, {open = true, keep = false} = {}) {

    const state = keep ? panel_state() : null;
    // keep: a refresh of the live updates
    const html = await get_html(`/show_details/${meta_file_id}/stage/${encodeURIComponent(stage_id)}`, {background: keep});

    // A rendered part of the server (docs/features/web-ui-scripts.md#rules, rule 4)
    const container = document.getElementById('stage-steps-container');
    container.innerHTML = html;
    const steps = panel();
    highlight(steps);
    select_node(stage_id);

    if (state) {
        restore_state(steps, state);
    } else {
        set_open(open, steps);
        if (open && steps.dataset.latestError) {
            scroll_to_step(steps.dataset.latestError, steps);
        }
    }
}


function stage_in_url() {
    const match = location.hash.match(/stage=(\d+)/);
    return match ? Number(match[1]) : null;
}


function init_panel() {

    const wanted = stage_in_url();
    const steps = panel();

    if (wanted !== null && wanted !== page.selected_stage_id) {
        load_steps(wanted, {open: true}).catch(show_error);
        return;
    }
    if (!steps) {
        return;
    }
    // Opened by itself only for a problem, or for a stage in the URL
    const open = steps.dataset.problem === 'true' || wanted !== null;
    set_open(open, steps);
    if (steps.dataset.problem === 'true' && steps.dataset.latestError) {
        scroll_to_step(steps.dataset.latestError, steps);
    }
}


on_action('select-stage', async (node) => {
    const stage_id = Number(node.dataset.stageId);
    history.replaceState(null, '', `#stage=${stage_id}`);
    try {
        await load_steps(stage_id, {open: true});
        panel()?.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    } catch (error) {
        show_error(error);
    }
});

on_action('toggle-steps', () => set_open(!is_open()));

on_action('toggle-step', (button) => {
    set_step_open(button.closest('.ir-step'), button.getAttribute('aria-expanded') !== 'true');
});

document.addEventListener('input', (event) => {
    if (event.target.matches('[data-action="filter-steps"]')) {
        apply_filter();
    }
});

on_change('only-problems', () => apply_filter());

init_panel();



//------------------------------------------------------------------------------
// Actions
//------------------------------------------------------------------------------

function started_message(stage_name, result) {
    // The stage is in the queue of the processing service, but nobody takes it from there
    if (result.mode === 'service' && !result.service_running) {
        return [`${stage_name} is queued: the processing service is not running. It runs as soon as the service is started.`, 'warning'];
    }
    return [`${stage_name} started`, 'success'];
}


on_action('run-stage', async (button) => {

    const {stageId, stageName, option} = button.dataset;
    const run = (chosen) => post_json(`/api/run_stage/${meta_file_id}/${stageId}/${chosen}`);
    let result = null;

    if (option) {
        // A button of the attention bar says what it does: one confirmation
        result = await confirm_action({
            title: option === 'run_all' ? `Run all steps of ${stageName}?` : `Run ${stageName}?`,
            text: option === 'run_all' ? 'All steps run again from the beginning, also those which are finished.' : 'The steps which are not finished run.',
            confirm: option === 'run_all' ? 'Run all steps' : 'Run',
            action: () => run(option),
        });
    } else {
        const chosen = await choose({
            title: `Run ${stageName}?`,
            text: 'Continue with the steps which are not finished, or run all steps from the beginning.',
            options: [{value: 'continue', label: 'Continue'}, {value: 'run_all', label: 'Run all steps'}],
        });
        if (chosen === null) {
            return;
        }
        try {
            result = await run(chosen);
        } catch (error) {
            if (error.status !== 401) {
                show_error(error);
            }
            return;
        }
    }

    if (result) {
        toast(...started_message(stageName, result));
        refresh_all();
    }
});


/** The form of "Run at…": date and time in the time zone of the browser, continue or all steps */
function schedule_form() {

    const form = document.createElement('div');
    form.className = 'text-start';

    const label = Object.assign(document.createElement('label'), {className: 'form-label fw-semibold', htmlFor: 'schedule-run-at', textContent: 'Date and time'});
    const input = Object.assign(document.createElement('input'), {type: 'datetime-local', id: 'schedule-run-at', className: 'form-control', required: true});
    // Earliest: the next minute. Proposed: the next full hour.
    const now = new Date();
    input.min = to_local_input(new Date(now.getTime() + 60000));
    const next_hour = new Date(now);
    next_hour.setHours(now.getHours() + 1, 0, 0, 0);
    input.value = to_local_input(next_hour);

    const zone = Object.assign(document.createElement('div'), {className: 'form-text', textContent: `Time zone of your browser: ${zone_name()}`});

    const options = document.createElement('div');
    options.className = 'mt-3';
    for (const [value, text, checked] of [['continue', 'Continue with the steps which are not finished', true], ['run_all', 'Run all steps from the beginning', false]]) {
        const check = Object.assign(document.createElement('div'), {className: 'form-check'});
        const radio = Object.assign(document.createElement('input'), {type: 'radio', name: 'schedule-option', id: `schedule-${value}`, value, checked, className: 'form-check-input'});
        const radio_label = Object.assign(document.createElement('label'), {className: 'form-check-label', htmlFor: `schedule-${value}`, textContent: text});
        check.append(radio, radio_label);
        options.append(check);
    }

    const note = Object.assign(document.createElement('p'), {className: 'form-text mt-3 mb-0',
        textContent: 'The processing service runs the stage at this time. Until then, no other stage of this deployment can be started. You can cancel the schedule until the run has started.'});

    form.append(label, input, zone, options, note);
    return {form, input, option: () => form.querySelector('input[name="schedule-option"]:checked').value};
}


on_action('schedule-stage', async (button) => {

    const {stageId, stageName} = button.dataset;
    const {form, input, option} = schedule_form();

    const result = await confirm_action({
        title: `Run ${stageName} at …`,
        confirm: 'Schedule',
        icon: null,
        html: form,
        action: () => {
            const run_at = local_input_to_iso(input.value);
            if (run_at === null) {
                throw new Error('Enter a date and time');
            }
            return post_json(`/api/run_stage/${meta_file_id}/${stageId}/${option()}`, {run_at});
        },
    });

    if (result) {
        const when = local_time_text(result.run_at) || result.run_at;
        if (result.service_running === false) {
            toast(`${stageName} is scheduled for ${when}. The processing service is not running: start it before then.`, 'warning');
        } else {
            toast(`${stageName} is scheduled for ${when}`);
        }
        refresh_all();
    }
});


on_action('cancel-schedule', (button) => confirm_and_refresh({
    title: `Cancel the scheduled run of ${button.dataset.stageName}?`,
    text: "The stage doesn't run at the scheduled time. It stays ready: run it or schedule it again.",
    confirm: 'Cancel schedule', cancel: 'Keep it', url: `/api/cancel_job/${button.dataset.jobId}`, done: `Scheduled run of ${button.dataset.stageName} canceled`,
}));


async function confirm_and_refresh({title, text, confirm, cancel = undefined, danger = false, url, done}) {
    const result = await confirm_action({title, text, confirm, cancel, danger, action: () => post_json(url)});
    if (result) {
        toast(done);
        refresh_all();
    }
}


on_action('reset-stage', (button) => confirm_and_refresh({
    title: `Reset ${button.dataset.stageName}?`,
    text: 'The stage hangs: its status is set back, so it can be run again. A job which still runs is not stopped.',
    confirm: 'Reset stage', url: `/api/reset_stage_status/${meta_file_id}/${button.dataset.stageId}`, done: `${button.dataset.stageName} reset`,
}));

on_action('reset-last-finished', (button) => confirm_and_refresh({
    title: `Reset ${button.dataset.stageName}?`,
    text: 'The stage is set back to ready, the stages after it to new. Its steps keep their status: choose "Run all steps" to run them again.',
    confirm: 'Reset stage', url: `/api/reset_last_finished_stage/${meta_file_id}/${button.dataset.stageId}`, done: `${button.dataset.stageName} reset`,
}));

on_action('reset-deployment', () => confirm_and_refresh({
    title: 'Reset the status of this deployment?',
    text: 'For a deployment which hangs. Its status is computed from its stages again.',
    confirm: 'Reset status', url: `/api/reset_deployment_status/${meta_file_id}`, done: 'Status reset',
}));

on_action('cancel-deployment', () => confirm_and_refresh({
    title: 'Cancel this deployment?',
    text: "It can't be continued afterwards. A stage which is running is not stopped.",
    confirm: 'Cancel deployment', danger: true, url: `/api/cancel_deployment/${meta_file_id}`, done: 'Deployment canceled',
}));

on_action('remove-from-queue', (button) => confirm_and_refresh({
    title: `Remove ${button.dataset.stageName} from the queue?`,
    text: "The stage waits for the processing service. It doesn't run if it's removed from the queue.",
    confirm: 'Remove from queue', url: `/api/cancel_job/${button.dataset.jobId}`, done: `${button.dataset.stageName} removed from the queue`,
}));


on_change('check-error', async (input) => {
    const stage_id = panel().dataset.stageId;
    const checked = input.checked;
    input.disabled = true;
    try {
        await post_json(`/api/set_check_error/${meta_file_id}/${stage_id}/${input.dataset.actionId}/${checked}`);
    } catch (error) {
        input.checked = !checked;
        if (error.status !== 401) {
            show_error(error);
        }
    } finally {
        input.disabled = false;
    }
});



//------------------------------------------------------------------------------
// Custom data
//------------------------------------------------------------------------------

// Text shown in the input field for the current value
function custom_field_text(field) {
    if (!field.exists || field.value === null) {
        return '';
    }
    return typeof field.value === 'object' ? JSON.stringify(field.value) : String(field.value);
}


// Converts the entered text back to the type the field had before
function parse_custom_field_value(field, text) {
    if (!field.exists || field.value === null) {
        return text;
    }
    if (typeof field.value === 'number') {
        const number = Number(text);
        if (text.trim() === '' || Number.isNaN(number)) {
            throw new Error(`'${field.path}' needs to be a number`);
        }
        return number;
    }
    if (typeof field.value === 'boolean') {
        if (!['true', 'false'].includes(text.trim().toLowerCase())) {
            throw new Error(`'${field.path}' needs to be true or false`);
        }
        return text.trim().toLowerCase() === 'true';
    }
    if (typeof field.value === 'object') {
        try {
            return JSON.parse(text);
        } catch {
            throw new Error(`'${field.path}' needs to be valid JSON`);
        }
    }
    return text;
}


on_action('edit-custom-data', async () => {

    const fields = page.editable_fields;
    const form = document.createElement('div');
    form.className = 'text-start';

    const inputs = fields.map((field, index) => {
        const label = document.createElement('label');
        label.className = 'form-label fw-semibold mt-2';
        label.htmlFor = `custom-field-${index}`;
        label.textContent = field.path;
        const input = document.createElement('input');
        input.type = 'text';
        input.id = `custom-field-${index}`;
        input.className = 'form-control';
        input.value = custom_field_text(field);
        form.append(label, input);
        return input;
    });

    const saved = await confirm_action({
        title: 'Edit custom data',
        confirm: 'Save',
        icon: null,
        action: async () => {
            const changed = {};
            fields.forEach((field, index) => {
                const text = inputs[index].value;
                if (text !== custom_field_text(field)) {
                    changed[field.path] = parse_custom_field_value(field, text);
                }
            });
            if (Object.keys(changed).length === 0) {
                return 'unchanged';
            }
            await post_json(`/api/edit_custom_data/${meta_file_id}`, {fields: changed});
            return 'saved';
        },
        html: form,
    });

    if (saved === 'saved') {
        toast('Custom data saved');
        refresh_all();
    }
});



//------------------------------------------------------------------------------
// Logs
//------------------------------------------------------------------------------

const log_dialog = document.getElementById('log-dialog');
const log = {output: '', errors: '', type: 'output', title: ''};


function show_log_text() {
    const pre = document.getElementById('log-text');
    const text = log[log.type];
    pre.textContent = text || (log.type === 'errors' ? 'No errors' : 'No output');
    pre.classList.toggle('empty', !text);
    log_dialog.querySelectorAll('[data-action="log-tab"]').forEach((tab) => {
        const active = tab.dataset.logType === log.type;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
    });
}


on_action('show-log', async (button) => {

    const {runId, logType, logSource, title} = button.dataset;

    try {
        if (logSource === 'deployment') {
            const data = await get_json(`/api/get_activity_log/${encodeURIComponent(runId)}`);
            Object.assign(log, {output: data.log || '', errors: '', type: 'output'});
        } else {
            const data = await get_json(`/api/get_action_log/${encodeURIComponent(runId)}`);
            Object.assign(log, {output: data.stdout || '', errors: data.stderr || '', type: logType === 'errors' ? 'errors' : 'output'});
        }
    } catch (error) {
        if (error.status !== 401) {
            show_error(error);
        }
        return;
    }

    log.title = title || 'Log';
    document.getElementById('log-dialog-title').textContent = log.title;
    document.getElementById('log-tabs').hidden = logSource === 'deployment';
    show_log_text();
    bootstrap.Modal.getOrCreateInstance(log_dialog).show();
});

on_action('log-tab', (tab) => {
    log.type = tab.dataset.logType;
    show_log_text();
});

on_change('log-wrap', (input) => {
    document.getElementById('log-text').classList.toggle('wrap', input.checked);
});

on_action('log-copy', async (button) => {
    try {
        await navigator.clipboard.writeText(log[log.type]);
        button.textContent = 'Copied';
    } catch {
        // http in the intranet: no clipboard API. Select the text, the user copies it.
        const range = document.createRange();
        range.selectNodeContents(document.getElementById('log-text'));
        getSelection().removeAllRanges();
        getSelection().addRange(range);
        button.textContent = 'Selected, press Ctrl+C';
    }
});

on_action('log-download', () => {
    const blob = new Blob([log[log.type]], {type: 'text/plain'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${log.title.replace(/[^\w.-]+/g, '_')}-${log.type}.log`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});

log_dialog.addEventListener('hidden.bs.modal', () => {
    log_dialog.querySelectorAll('[data-action="log-copy"]').forEach((button) => {
        button.replaceChildren(Object.assign(document.createElement('i'), {className: 'bi bi-copy'}), ' Copy');
    });
});



//------------------------------------------------------------------------------
// Live updates (docs/features/web-ui-live-updates.md)
//
// /api/watch_state pushes hashes of the deployment: `parts` (header, flow, objects, activity) and `stages`.
// A changed part is taken from the page, loaded in the background (at most once a second), and replaced in place.
// The objects table gets its new rows, the steps panel its stage again. Nothing loads the whole page again.
//------------------------------------------------------------------------------

// Hash of the server -> parts of the page it changes
const PARTS_OF = {
    header: ['header', 'details', 'attention'],
    flow: ['flow', 'attention'],
    activity: ['activity'],
};
const ALL_PARTS = ['header', 'details', 'attention', 'flow', 'activity'];
const LOAD_INTERVAL_MS = 1000;
const RETRY_MS = [2000, 5000, 10000, 30000];

let signature = null;
let source = null;
let stopped = false;
let attempts = 0;
let retry_timer = null;

const pending = new Set();
let loading = false;
let load_timer = null;
let last_load = 0;


/** Elements of a part which keep their state when the part is replaced */
function keep_state(name, element) {
    if (name === 'activity') {
        return {tab: element.querySelector('.nav-link.active')?.id};
    }
    if (name === 'details') {
        return {open: element.querySelector('details.ir-custom-data')?.open};
    }
    return {};
}


function restore(name, element, state) {
    if (name === 'flow') {
        select_node(panel()?.dataset.stageId);
    } else if (name === 'details') {
        const details = element.querySelector('details.ir-custom-data');
        if (details && state.open) {
            details.open = true;
        }
        highlight(element);
    } else if (name === 'activity') {
        element.querySelectorAll('table[data-toggle="table"]').forEach((table) => $(table).bootstrapTable());
        if (state.tab && state.tab !== 'activity-actions-tab') {
            const tab = document.getElementById(state.tab);
            if (tab) {
                bootstrap.Tab.getOrCreateInstance(tab).show();
            }
        }
    }
}


function replace_part(name, loaded) {
    const current = document.querySelector(`[data-part="${name}"]`);
    const next = loaded.querySelector(`[data-part="${name}"]`);
    if (!current || !next) {
        return;
    }
    const state = keep_state(name, current);
    // Parsed from a page of the server (rule 4 of docs/features/web-ui-scripts.md#rules); its scripts don't run
    const element = document.importNode(next, true);
    current.replaceWith(element);
    restore(name, element, state);
}


async function load_parts() {

    load_timer = null;
    if (loading || pending.size === 0 || stopped) {
        return;
    }

    loading = true;
    last_load = Date.now();
    const names = [...pending];
    pending.clear();

    try {
        const html = await get_html(`/show_details/${meta_file_id}`, {background: true});
        const loaded = new DOMParser().parseFromString(html, 'text/html');
        names.forEach((name) => replace_part(name, loaded));
        document.title = loaded.title;
    } catch (error) {
        if (error.status === 401) {
            stop();
            return;
        }
        // Not reachable: loaded again with the next change or after the connection is back
        names.forEach((name) => pending.add(name));
    } finally {
        loading = false;
    }

    schedule_load();
}


function schedule_load() {
    if (load_timer !== null || loading || pending.size === 0 || stopped) {
        return;
    }
    load_timer = setTimeout(load_parts, Math.max(0, last_load + LOAD_INTERVAL_MS - Date.now()));
}


function request_parts(names) {
    names.forEach((name) => pending.add(name));
    schedule_load();
}


function refresh_steps() {
    const steps = panel();
    if (steps) {
        load_steps(steps.dataset.stageId, {keep: true}).catch(() => {});
    }
}


async function refresh_objects() {
    if (!objects) {
        return;
    }
    try {
        const count = await objects.refresh();
        const badge = document.querySelector('[data-objects-count]');
        if (badge) {
            badge.textContent = String(count);
        }
    } catch (error) {
        if (error.status === 401) {
            stop();
        }
    }
}


/** Everything once: after an action, after the connection is back, when the tab is shown again */
function refresh_all() {
    request_parts(ALL_PARTS);
    refresh_objects();
    refresh_steps();
}


function handle_signature(next) {

    if (next.status === 'error') {
        // The deployment doesn't exist any more
        stop();
        return;
    }

    const previous = signature;
    signature = next;
    if (previous === null) {
        return;
    }

    const changed = Object.keys(next.parts || {}).filter((name) => previous.parts?.[name] !== next.parts[name]);
    const stages_changed = Object.keys(next.stages).some((id) => previous.stages[id] !== next.stages[id]);

    const names = new Set(changed.flatMap((name) => PARTS_OF[name] || []));
    // The attention bar says which step runs
    if (stages_changed) {
        names.add('attention');
    }
    if (names.size > 0) {
        request_parts([...names]);
    }

    if (changed.includes('objects')) {
        refresh_objects();
    }

    // The steps of the selected stage; its buttons depend on the deployment too
    const stage_id = panel()?.dataset.stageId;
    if (stage_id && (previous.stages[stage_id] !== next.stages[stage_id] || changed.includes('header') || changed.includes('flow'))) {
        refresh_steps();
    }
}


function set_reconnecting(on) {
    document.querySelector('.ir-reconnecting').hidden = !on;
}


function connect() {

    if (stopped) {
        return;
    }

    source = new EventSource(`/api/watch_state/${meta_file_id}`);

    source.onopen = () => {
        if (attempts > 0) {
            attempts = 0;
            set_reconnecting(false);
        }
    };

    source.onmessage = (event) => handle_signature(JSON.parse(event.data));

    // The browser would retry forever, also after the session has ended: the page decides
    source.onerror = () => {
        source.close();
        if (!stopped && !document.hidden) {
            reconnect_later();
        }
    };
}


function reconnect_later() {

    set_reconnecting(true);
    const delay = RETRY_MS[Math.min(attempts, RETRY_MS.length - 1)];
    attempts++;

    clearTimeout(retry_timer);
    retry_timer = setTimeout(async () => {
        try {
            // Reachable, and still logged in? (401: "Your session has ended", see app/api.js)
            await get_html(`/show_details/${meta_file_id}/stage/${encodeURIComponent(panel()?.dataset.stageId || page.selected_stage_id)}`, {background: true});
        } catch (error) {
            if (error.status === 401) {
                stop();
            } else if (!stopped) {
                reconnect_later();
            }
            return;
        }
        // What changed meanwhile
        signature = null;
        refresh_all();
        connect();
    }, delay);
}


/** The session has ended or the deployment is gone: no more updates */
function stop() {
    stopped = true;
    source?.close();
    clearTimeout(retry_timer);
    clearTimeout(load_timer);
    set_reconnecting(false);
}


document.addEventListener('visibilitychange', () => {
    if (stopped) {
        return;
    }
    if (document.hidden) {
        source?.close();
        clearTimeout(retry_timer);
    } else if (!source || source.readyState === EventSource.CLOSED) {
        signature = null;
        refresh_all();
        connect();
    }
});

connect();


// Four-eyes check (docs/features/four-eyes-check.md)
on_action('approve-stage', (button) => confirm_and_refresh({
    title: `Approve ${button.dataset.stageName}?`,
    text: 'You confirm the objects and the custom data of this deployment as they are now. Another person runs the stage; a change afterwards needs a new approval.',
    confirm: 'Approve', url: `/api/approve_stage/${meta_file_id}/${button.dataset.stageId}`, done: `${button.dataset.stageName} approved`,
}));
