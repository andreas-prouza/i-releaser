/*
 * Small helpers for the scripts of the pages (docs/features/web-ui-scripts.md#rules).
 *
 * Templates give data to scripts with data-* attributes or a JSON block, never as generated JavaScript:
 *
 *     <button type="button" data-action="run-stage" data-stage-id="{{ stage.id }}">Run stage</button>
 *     <script type="application/json" id="page-data">{{ page_data | tojson }}</script>
 *
 *     on_action('run-stage', (button) => run_stage(button.dataset.stageId));
 *     const data = read_json('page-data');
 */


/** Click on an element with data-action="<name>" (also elements added later). Disabled elements are ignored. */
export function on_action(name, handler) {
    document.addEventListener('click', (event) => {
        const element = event.target.closest(`[data-action="${CSS.escape(name)}"]`);
        if (!element || element.disabled || element.getAttribute('aria-disabled') === 'true') {
            return;
        }
        event.preventDefault();
        handler(element, event);
    });
}


/** Change of an input or select with data-action="<name>" */
export function on_change(name, handler) {
    document.addEventListener('change', (event) => {
        const element = event.target.closest(`[data-action="${CSS.escape(name)}"]`);
        if (element) {
            handler(element, event);
        }
    });
}


/** The content of <script type="application/json" id="..."> */
export function read_json(id) {
    const element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : null;
}


/** Only for HTML which can't be built with the DOM API (e.g. the html option of SweetAlert2). Prefer textContent. */
export function escape_html(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}


/** An element with text: element('code', token) */
export function element(tag, text = '', attributes = {}) {
    const node = document.createElement(tag);
    node.textContent = text;
    for (const [name, value] of Object.entries(attributes)) {
        node.setAttribute(name, value);
    }
    return node;
}
