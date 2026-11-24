/*
 * Administration, part System (templates/admin/settings.html)
 *
 * Send a test message with a channel of the notifications (docs/features/notifications.md),
 * remove the old deployments now (docs/features/data-retention.md).
 */
import { post_json } from '../app/api.js';
import { confirm_action, reload_with_toast, toast } from '../app/dialogs.js';
import { element, on_action } from '../app/dom.js';


on_action('test-notification', async (button) => {

    const {channel, type, mail} = button.dataset;
    let html;
    let input = null;

    // An e-mail channel: the address for the test, the own one by default
    if (type === 'email') {
        html = element('div', '', {class: 'text-start'});
        const label = element('label', 'Send the test to', {for: 'notification-test-recipient', class: 'form-label'});
        input = element('input', '', {id: 'notification-test-recipient', type: 'email', class: 'form-control', autocomplete: 'email'});
        input.value = mail || '';
        html.append(label, input);
    }

    const result = await confirm_action({
        title: `Send a test message with the channel ${channel}?`,
        text: type === 'email' ? '' : 'It is sent to the webhook of the channel now.',
        html,
        confirm: 'Send',
        action: () => post_json(`/api/notifications/test/${encodeURIComponent(channel)}`, input ? {recipient: input.value.trim()} : {}),
    });

    if (result) {
        toast(`Test message sent to ${result.sent_to}`);
    }
});


on_action('run-retention', async () => {

    const result = await confirm_action({
        title: 'Remove the old deployments now?',
        text: "They are removed with their files. This can't be undone (unless they are archived).",
        confirm: 'Remove',
        danger: true,
        action: () => post_json('/api/retention/run'),
    });

    if (result) {
        reload_with_toast(`${result.removed.length} deployments removed`);
    }
});
