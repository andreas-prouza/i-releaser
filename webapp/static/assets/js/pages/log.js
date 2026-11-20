/*
 * A log file (templates/admin/log.html, docs/features/web-ui-admin-pages.md#logs)
 *
 * Number of lines and file: a new page. Level and search filter the loaded lines in the browser; both stay in the
 * URL (?level=WARNING&q=...), so a reload and the other choices keep them.
 */
import { on_action, on_change } from '../app/dom.js';


const LEVELS = {all: null, WARNING: ['WARNING', 'ERROR', 'CRITICAL'], ERROR: ['ERROR', 'CRITICAL']};

const level = document.getElementById('log-level');
const search = document.getElementById('log-search');
const count = document.getElementById('log-count');
const lines = [...document.querySelectorAll('.ir-log-line')];


function query() {
    const params = new URLSearchParams();
    if (level.value !== 'all') {
        params.set('level', level.value);
    }
    if (search.value.trim()) {
        params.set('q', search.value.trim());
    }
    const text = params.toString();
    return text ? `?${text}` : '';
}


function apply_filter() {
    const allowed = LEVELS[level.value];
    const text = search.value.trim().toLowerCase();
    let shown = 0;
    for (const line of lines) {
        const visible = (!allowed || allowed.includes(line.dataset.level)) && (!text || line.textContent.toLowerCase().includes(text));
        line.hidden = !visible;
        if (visible) {
            shown++;
        }
    }
    count.textContent = shown === lines.length ? `${lines.length} lines` : `${shown} of ${lines.length} lines`;
    history.replaceState(null, '', `${location.pathname}${query()}`);
}


function file_url(file, number) {
    return `/log/${encodeURIComponent(file)}/${encodeURIComponent(number)}${query()}`;
}


on_change('log-lines', (select) => {
    location.href = file_url(select.dataset.logfile, select.value);
});

on_change('log-file', (select) => {
    location.href = file_url(select.value, document.getElementById('number_of_lines').value);
});

on_change('log-level', apply_filter);

search.addEventListener('input', apply_filter);

on_action('log-refresh', () => location.reload());

apply_filter();
