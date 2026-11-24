/*
 * Dialogs and messages with SweetAlert2 (docs/features/web-ui-scripts.md).
 *
 * - confirm_action: for actions which can't be undone. One dialog; it waits for the server and shows its error.
 * - choose: one of two ways to do an action (e.g. Continue / Run all steps)
 * - toast: the result of an action, a short message which disappears. reload_with_toast shows it after a reload.
 * - show_error: an error, stays until it's closed
 * A canceled dialog shows nothing.
 */

const TOAST_KEY = 'ir-toast';
const TOAST_MS = 3500;

// Buttons of Bootstrap; customClass of a single dialog replaces this one, see dialog_classes()
const dialog = Swal.mixin({
    buttonsStyling: false,
    reverseButtons: true,
    customClass: dialog_classes(),
});

let session_dialog_open = false;



function error_message(error) {
    return error?.message || String(error);
}



/**
 * Asks before an action. `action` (async) runs while the dialog shows a loader; an error of it is shown in the dialog.
 * `html`: an element instead of the text (e.g. a small form; built with the DOM, not from text).
 * Returns the result of `action` (or true without action), null if canceled.
 */
export async function confirm_action({title, text = '', html = undefined, icon = undefined, confirm, cancel = 'Cancel', danger = false, action = null}) {

    // The action needs a recent code of the authenticator app (app/api.js): the dialog closes, the code is asked, the action runs again
    const STEP_UP = {};

    const result = await dialog.fire({
        title,
        text,
        html,
        icon: icon !== undefined ? icon : danger ? 'warning' : 'question',
        showCancelButton: true,
        confirmButtonText: confirm,
        cancelButtonText: cancel,
        customClass: {...dialog_classes(), confirmButton: danger ? 'btn btn-danger' : 'btn btn-primary'},
        focusCancel: danger,
        showLoaderOnConfirm: action !== null,
        allowOutsideClick: () => !Swal.isLoading(),
        preConfirm: action === null ? undefined : async () => {
            try {
                return (await action()) ?? true;
            } catch (error) {
                if (error?.status === 401) {
                    return false;
                }
                if (error?.data?.step_up) {
                    return STEP_UP;
                }
                Swal.showValidationMessage(error_message(error));
                return false;
            }
        },
    });

    if (result.isConfirmed && result.value === STEP_UP) {
        // Loaded here: api.js imports this module
        const { verify_code } = await import('./api.js');
        if (!await ask_code({verify: verify_code})) {
            return null;
        }
        try {
            return (await action()) ?? true;
        } catch (error) {
            show_error(error);
            return null;
        }
    }

    return result.isConfirmed ? (result.value ?? true) : null;
}



/**
 * Two ways to do an action: options = [{value, label}, {value, label}]. Returns the value, null if canceled.
 */
export async function choose({title, text = '', options, cancel = 'Cancel'}) {

    const [first, second] = options;
    const result = await dialog.fire({
        title,
        text,
        icon: 'question',
        showDenyButton: second !== undefined,
        showCancelButton: true,
        confirmButtonText: first.label,
        denyButtonText: second?.label,
        cancelButtonText: cancel,
    });

    if (result.isConfirmed) {
        return first.value;
    }
    return result.isDenied ? second.value : null;
}



export function toast(message, icon = 'success') {
    return Swal.fire({
        toast: true,
        position: 'top-end',
        icon,
        title: message,
        showConfirmButton: false,
        timer: TOAST_MS,
        timerProgressBar: true,
    });
}



/** For a change the page shows only after a reload: the toast comes after it */
export function reload_with_toast(message, icon = 'success') {
    try {
        sessionStorage.setItem(TOAST_KEY, JSON.stringify({message, icon}));
    } catch {
        // no toast, the page shows the change
    }
    location.reload();
}



export function show_error(error, title = 'Error') {
    return dialog.fire({icon: 'error', title, text: error_message(error), confirmButtonText: 'Close'});
}



/** The server answered 401: shown once, the button opens the login and comes back to this page */
export function session_ended() {

    if (session_dialog_open) {
        return;
    }
    session_dialog_open = true;

    dialog.fire({
        icon: 'info',
        title: 'Your session has ended',
        text: 'Log in again to continue. What you did last was not saved.',
        confirmButtonText: 'Log in',
        allowOutsideClick: false,
    }).then((result) => {
        session_dialog_open = false;
        if (result.isConfirmed) {
            location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
        }
    });
}



function dialog_classes() {
    return {
        confirmButton: 'btn btn-primary',
        denyButton: 'btn btn-outline-secondary',
        cancelButton: 'btn btn-outline-secondary',
        actions: 'ir-dialog-actions',
    };
}



// The toast of reload_with_toast
try {
    const stored = sessionStorage.getItem(TOAST_KEY);
    if (stored) {
        sessionStorage.removeItem(TOAST_KEY);
        const {message, icon} = JSON.parse(stored);
        toast(message, icon);
    }
} catch {
    // sessionStorage switched off
}


/**
 * Asks for the code of the authenticator app (docs/features/two-factor-authentication.md).
 * `verify(code)` (async) checks it; its error is shown in the dialog, so the user can try again.
 * Returns true if a code has been verified, false if canceled.
 */
export async function ask_code({title = 'Confirm with your authenticator app', text = 'Enter the current code of your authenticator app, or a recovery code.', confirm = 'Confirm', verify}) {

    const result = await dialog.fire({
        title,
        text,
        input: 'text',
        inputAttributes: {autocomplete: 'one-time-code', inputmode: 'numeric', autocapitalize: 'none', spellcheck: 'false', maxlength: '20', 'aria-label': 'Code'},
        showCancelButton: true,
        confirmButtonText: confirm,
        cancelButtonText: 'Cancel',
        showLoaderOnConfirm: true,
        allowOutsideClick: () => !Swal.isLoading(),
        preConfirm: async (code) => {
            try {
                await verify((code || '').trim());
                return true;
            } catch (error) {
                Swal.showValidationMessage(error_message(error));
                return false;
            }
        },
    });

    return result.isConfirmed;
}
