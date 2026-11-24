/*
 * Settings, general part (templates/admin/settings.html)
 *
 * Unblock the login of a user (docs/bugfixes/login-can-disable-ibm-i-profiles.md), reset the two-factor authentication of a user,
 * send a test message with a channel of the notifications (docs/features/notifications.md).
 */
import { delete_json, post_json } from '../app/api.js';
import { confirm_action, reload_with_toast, toast } from '../app/dialogs.js';
import { element, on_action } from '../app/dom.js';


on_action('unblock-login', async (button) => {

    const user = button.dataset.user;

    const done = await confirm_action({
        title: `Unblock the login of ${user}?`,
        text: 'Each further wrong password counts again for the IBM i. Unblock only after you know who has tried.',
        confirm: 'Unblock',
        action: () => post_json(`/api/unblock_login/${encodeURIComponent(user)}`),
    });

    if (done) {
        reload_with_toast(`Login of ${user} unblocked`);
    }
});


on_action('reset-mfa', async (button) => {

    const user = button.dataset.user;

    const done = await confirm_action({
        title: `Reset the two-factor authentication of ${user}?`,
        text: 'The user sets it up again at the next login (or can log in with the password only, if it is not required).',
        confirm: 'Reset',
        danger: true,
        action: () => post_json(`/api/mfa/reset/${encodeURIComponent(user)}`),
    });

    if (done) {
        reload_with_toast(`Two-factor authentication of ${user} reset`);
    }
});


on_action('revoke-token', async (button) => {

    const {user, name, tokenId} = button.dataset;

    const done = await confirm_action({
        title: `Revoke the API token ${name} of ${user}?`,
        text: "Clients which use it can't log in with it any more. The user can create a new one.",
        confirm: 'Revoke',
        danger: true,
        action: () => delete_json(`/api/v2/tokens/${encodeURIComponent(tokenId)}`),
    });

    if (done) {
        reload_with_toast(`Token ${name} of ${user} revoked`);
    }
});


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
