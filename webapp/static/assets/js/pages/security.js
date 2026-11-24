/*
 * Administration, part Security (templates/admin/security.html)
 *
 * Revoke the API token of a user (docs/features/api-v2.md#tokens), reset the two-factor authentication of a user,
 * unblock the login of a user (docs/bugfixes/login-can-disable-ibm-i-profiles.md).
 */
import { delete_json, post_json } from '../app/api.js';
import { confirm_action, reload_with_toast } from '../app/dialogs.js';
import { on_action } from '../app/dom.js';


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
