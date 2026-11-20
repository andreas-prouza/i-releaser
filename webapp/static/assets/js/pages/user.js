/*
 * User page: the token for the Web API (templates/admin/user.html)
 */
import { post_json } from '../app/api.js';
import { confirm_action, reload_with_toast } from '../app/dialogs.js';
import { element, on_action } from '../app/dom.js';


on_action('renew-token', async (button) => {

    const data = await confirm_action({
        title: 'Generate a new token?',
        text: button.dataset.hasToken === 'true' ? "Clients which use the current token can't log in with it any more." : '',
        confirm: 'Generate token',
        action: () => post_json('/api/generate_user_key'),
    });

    if (!data) {
        return;
    }

    // The token is shown once and never written anywhere else (no console). Copy: like code_block (app/components.js)
    const text = element('div');
    const block = element('div', '', {class: 'ir-code text-start'});
    const pre = element('pre');
    pre.append(element('code', data.token));
    const copy = element('button', '', {type: 'button', class: 'ir-copy', 'data-copy': '', 'aria-label': 'Copy the token', title: 'Copy the token'});
    copy.append(element('i', '', {class: 'bi bi-copy', 'aria-hidden': 'true'}));
    block.append(pre, copy);
    text.append(element('p', "Your token. It is shown only once and can't be shown again: copy it now."), block);
    await Swal.fire({title: 'Token generated', html: text, icon: 'success', confirmButtonText: 'Done'});

    location.reload();
});


on_action('delete-token', async () => {

    const deleted = await confirm_action({
        title: 'Delete your token?',
        text: "Clients which use it can't log in with it any more.",
        confirm: 'Delete token',
        cancel: 'Keep it',
        danger: true,
        action: () => post_json('/api/drop_key'),
    });

    if (deleted) {
        reload_with_toast('Token deleted');
    }
});
