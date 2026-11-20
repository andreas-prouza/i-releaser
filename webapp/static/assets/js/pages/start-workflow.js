/*
 * Start of a workflow (docs/features/web-ui-lists.md#start-of-a-workflow): `Start workflow` of the deployment list
 * and `Start` of the page Workflows. One dialog: the workflow, one field per path of its `create_fields`.
 *
 * The workflows the user may start come from the JSON block #start-workflows (routes.get_startable_workflows).
 * A button with data-workflow starts that workflow, without it the dialog asks for one.
 */
import { post_json } from '../app/api.js';
import { confirm_action } from '../app/dialogs.js';
import { element, on_action, read_json } from '../app/dom.js';


const workflows = read_json('start-workflows') || [];


/** {"jira": {"issue": "X-1"}} from the keys ["jira", "issue"] */
function set_value(data, keys, value) {
    let target = data;
    keys.slice(0, -1).forEach((key) => {
        target[key] = typeof target[key] === 'object' && target[key] !== null ? target[key] : {};
        target = target[key];
    });
    target[keys[keys.length - 1]] = value;
}


function build_form(selected) {

    const form = element('div');
    form.className = 'text-start ir-start-form';

    let select = null;
    if (!selected) {
        const label = element('label', 'Workflow', {for: 'start-workflow-name', class: 'form-label fw-semibold'});
        select = element('select', '', {id: 'start-workflow-name', class: 'form-select'});
        workflows.forEach((wf) => select.append(element('option', wf.name, {value: wf.name})));
        form.append(label, select);
    }

    const fields = element('div');
    form.append(fields);

    const show_fields = () => {
        const wf = workflows.find((w) => w.name === (selected || select.value));
        fields.replaceChildren();
        (wf?.fields || []).forEach((field, index) => {
            const id = `start-field-${index}`;
            fields.append(
                element('label', field.label, {for: id, class: 'form-label fw-semibold mt-3'}),
                element('input', '', {id, type: 'text', class: 'form-control', 'data-keys': JSON.stringify(field.keys)}),
            );
        });
        if (!wf?.fields?.length) {
            fields.append(element('p', 'A new deployment of this workflow is created.', {class: 'mt-3 mb-0 text-body-secondary'}));
        }
    };

    select?.addEventListener('change', show_fields);
    show_fields();

    return {form, workflow: () => selected || select.value};
}


on_action('start-workflow', async (button) => {

    if (workflows.length === 0) {
        return;
    }

    const {form, workflow} = build_form(button.dataset.workflow);

    const data = await confirm_action({
        title: button.dataset.workflow ? `Start ${button.dataset.workflow}?` : 'Start a workflow',
        html: form,
        icon: null,
        confirm: 'Start',
        action: () => {
            const custom_data = {};
            form.querySelectorAll('input[data-keys]').forEach((input) => {
                if (input.value.trim() !== '') {
                    set_value(custom_data, JSON.parse(input.dataset.keys), input.value.trim());
                }
            });
            return post_json(`/api/start_workflow/${encodeURIComponent(workflow())}`, custom_data);
        },
    });

    if (data) {
        location.href = `/show_details/${encodeURIComponent(data.meta_file.general.id)}`;
    }
});
