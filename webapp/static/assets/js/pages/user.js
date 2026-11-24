/*
 * User page: the tokens for the Web API (docs/features/api-v2.md#tokens), the two-factor authentication (templates/admin/user.html,
 * docs/features/two-factor-authentication.md)
 */
import { delete_json, post_json } from '../app/api.js';
import { ask_code, confirm_action, reload_with_toast } from '../app/dialogs.js';
import { element, on_action } from '../app/dom.js';


/** A block with a text and a copy button (like code_block of app/components.js) */
function copy_block(text, label) {
    const block = element('div', '', {class: 'ir-code text-start'});
    const pre = element('pre');
    pre.append(element('code', text));
    const copy = element('button', '', {type: 'button', class: 'ir-copy', 'data-copy': '', 'aria-label': label, title: label});
    copy.append(element('i', '', {class: 'bi bi-copy', 'aria-hidden': 'true'}));
    block.append(pre, copy);
    return block;
}


async function show_recovery_codes(codes) {
    const content = element('div');
    content.append(element('p', "Keep these codes in a safe place. Each logs in once without the app, e.g. if you lose your phone. They are shown only once."),
                   copy_block(codes.join('\n'), 'Copy the recovery codes'));
    await Swal.fire({title: 'Recovery codes', html: content, icon: 'info', confirmButtonText: 'I have saved them', allowOutsideClick: false});
}


on_action('mfa-setup', async () => {

    let setup;
    try {
        setup = await post_json('/api/mfa/setup');
    } catch (error) {
        await Swal.fire({title: 'Error', text: error.message, icon: 'error'});
        return;
    }

    // Built with the DOM; the QR code is an image (data URI), not HTML
    const content = element('div');
    const image = element('img', '', {src: setup.qr_code, alt: 'QR code for the authenticator app', width: '220', height: '220', class: 'ir-qr-code'});
    content.append(element('p', '1. Scan the QR code with your authenticator app, or enter the key by hand.'), image,
                   copy_block(setup.secret, 'Copy the key'), element('p', '2. Enter the code the app shows.', {class: 'mt-3 mb-0'}));

    let recovery_codes = null;
    const result = await Swal.fire({
        title: 'Set up two-factor authentication',
        html: content,
        input: 'text',
        inputAttributes: {autocomplete: 'one-time-code', inputmode: 'numeric', maxlength: '6', 'aria-label': 'Code of the app'},
        showCancelButton: true,
        confirmButtonText: 'Activate',
        showLoaderOnConfirm: true,
        allowOutsideClick: () => !Swal.isLoading(),
        preConfirm: async (code) => {
            try {
                recovery_codes = (await post_json('/api/mfa/enable', {code: (code || '').trim()})).recovery_codes;
                return true;
            } catch (error) {
                Swal.showValidationMessage(error.message);
                return false;
            }
        },
    });

    if (!result.isConfirmed) {
        return;
    }

    await show_recovery_codes(recovery_codes);
    reload_with_toast('Two-factor authentication is active');
});


on_action('mfa-disable', async () => {

    const done = await ask_code({
        title: 'Turn off two-factor authentication?',
        text: 'Enter a code of your authenticator app (or a recovery code). Afterwards the login needs only your password.',
        confirm: 'Turn off',
        verify: (code) => post_json('/api/mfa/disable', {code}),
    });

    if (done) {
        reload_with_toast('Two-factor authentication turned off');
    }
});


on_action('mfa-recovery-codes', async () => {

    const data = await confirm_action({
        title: 'Create new recovery codes?',
        text: 'The recovery codes you have now are no longer valid.',
        confirm: 'Create',
        action: () => post_json('/api/mfa/recovery_codes'),
    });

    if (data) {
        await show_recovery_codes(data.recovery_codes);
        location.reload();
    }
});


/** The form of a new token: name, scope, days (built with the DOM) */
function token_form(max_days) {

    const form = element('div', '', {class: 'text-start'});

    const name = element('input', '', {id: 'token-name', type: 'text', class: 'form-control', maxlength: '64', autocomplete: 'off'});
    name.value = 'OBI extension';

    const scope = element('select', '', {id: 'token-scope', class: 'form-select'});
    for (const [value, text] of [['write', 'write: all actions of your permissions'], ['read', 'read: only reads']]) {
        const option = element('option', text, {value});
        scope.append(option);
    }

    const days = element('input', '', {id: 'token-days', type: 'number', class: 'form-control', min: '1'});
    if (max_days > 0) {
        days.max = String(max_days);
        days.value = String(max_days);
    }

    for (const [label, field] of [['Name', name], ['Scope', scope], [max_days > 0 ? `Expires after days (at most ${max_days})` : 'Expires after days (empty: never)', days]]) {
        const group = element('div', '', {class: 'mb-3'});
        group.append(element('label', label, {for: field.id, class: 'form-label'}), field);
        form.append(group);
    }

    return {form, values: () => ({name: name.value.trim(), scope: scope.value, ...(days.value ? {expires_in_days: Number(days.value)} : {})})};
}


on_action('new-token', async (button) => {

    const {form, values} = token_form(Number(button.dataset.maxDays || 0));

    const data = await confirm_action({
        title: 'New API token',
        html: form,
        icon: '',
        confirm: 'Create token',
        action: () => post_json('/api/v2/tokens', values()),
    });

    if (!data) {
        return;
    }

    // The token is shown once and never written anywhere else (no console). Copy: like code_block (app/components.js)
    const text = element('div');
    text.append(element('p', "Your token. It is shown only once and can't be shown again: copy it now."), copy_block(data.token, 'Copy the token'));
    await Swal.fire({title: `Token ${data.name} created`, html: text, icon: 'success', confirmButtonText: 'Done'});

    location.reload();
});


on_action('delete-token', async (button) => {

    const deleted = await confirm_action({
        title: `Delete your token ${button.dataset.name}?`,
        text: "Clients which use it can't log in with it any more.",
        confirm: 'Delete token',
        cancel: 'Keep it',
        danger: true,
        action: () => delete_json(`/api/v2/tokens/${encodeURIComponent(button.dataset.tokenId)}`),
    });

    if (deleted) {
        reload_with_toast('Token deleted');
    }
});
