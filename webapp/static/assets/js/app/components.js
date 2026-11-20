/*
 * Behaviour of the components of templates/components/ui.html, loaded by base.html on every page.
 *
 * code_block: the copy button copies the text of its block. A button with data-copy-text copies that text.
 */

const COPIED_MS = 1500;


// navigator.clipboard only exists on https and localhost; the web app often runs on http in the intranet
async function copy_text(text) {
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    if (!copied) {
        throw new Error('The browser did not allow to copy');
    }
}


function show_result(button, icon, label) {
    const original = {icon: button.querySelector('.bi').className, label: button.getAttribute('aria-label')};
    button.querySelector('.bi').className = `bi ${icon}`;
    button.setAttribute('aria-label', label);
    button.title = label;
    setTimeout(() => {
        button.querySelector('.bi').className = original.icon;
        button.setAttribute('aria-label', original.label);
        button.title = original.label;
    }, COPIED_MS);
}


document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy], [data-copy-text]');
    if (!button) {
        return;
    }
    const text = button.dataset.copyText ?? button.closest('.ir-code')?.querySelector('code, pre')?.textContent;
    if (text === undefined) {
        return;
    }
    try {
        await copy_text(text);
        show_result(button, 'bi-check2', 'Copied');
    } catch (error) {
        show_result(button, 'bi-exclamation-triangle', error.message);
    }
});
