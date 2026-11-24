/*
 * Administration, part Settings (templates/admin/configuration.html, docs/features/settings-in-web-app.md)
 *
 * Save a setting of the web app, or reset it to the value of etc/settings.py or the default.
 * A recent code of the two-factor authentication is asked by app/api.js when it's needed.
 */
import { delete_json, post_json } from '../app/api.js';
import { confirm_action, reload_with_toast, show_error } from '../app/dialogs.js';
import { on_action } from '../app/dom.js';


/** The value of the field of a setting, as the server expects it; null if it's not a number where one is needed */
function read_value(row) {
    const input = row.querySelector('[data-setting-input]');
    const kind = row.dataset.kind;
    if (kind === 'bool') {
        return input.checked;
    }
    if (kind === 'text') {
        return input.value.trim();
    }
    if (input.value.trim() === '' || Number.isNaN(Number(input.value))) {
        return null;
    }
    return Number(input.value);
}


on_action('save-setting', async (button) => {

    const name = button.dataset.name;
    const value = read_value(button.closest('tr'));

    if (value === null) {
        show_error(new Error(`${name} has to be a number`), 'Not saved');
        return;
    }

    try {
        await post_json(`/api/settings/${encodeURIComponent(name)}`, {value});
    } catch (error) {
        if (error.status !== 401) {
            show_error(error, 'Not saved');
        }
        return;
    }
    reload_with_toast(`${name} saved`);
});


on_action('reset-setting', async (button) => {

    const name = button.dataset.name;

    const done = await confirm_action({
        title: `Reset ${name}?`,
        text: 'The value of etc/settings.py or the default counts again.',
        confirm: 'Reset',
        action: () => delete_json(`/api/settings/${encodeURIComponent(name)}`),
    });

    if (done) {
        reload_with_toast(`${name} reset`);
    }
});
