/*
 * Times with time zone (e.g. a scheduled run, docs/features/scheduled-stage-run.md) in the time zone of the browser.
 *
 * The server renders <time datetime="2026-11-24T21:00:00+00:00" data-local-time>2026-11-24 21:00 UTC</time>
 * (macro local_time of templates/components/ui.html). components.js replaces the text on every page,
 * also in parts which are loaded later.
 */

const pad = (n) => String(n).padStart(2, '0');


/** Name of the time zone of the browser, e.g. 'CET' or 'GMT+1' */
export function zone_name(date = new Date()) {
    try {
        const part = new Intl.DateTimeFormat(undefined, {timeZoneName: 'short'}).formatToParts(date).find((p) => p.type === 'timeZoneName');
        if (part) {
            return part.value;
        }
    } catch {
        // an old browser: the offset below
    }
    return `UTC${offset_text(date)}`;
}


/** Offset of the browser's time zone at this date, e.g. '+01:00' */
export function offset_text(date) {
    const minutes = -date.getTimezoneOffset();
    const sign = minutes >= 0 ? '+' : '-';
    return `${sign}${pad(Math.floor(Math.abs(minutes) / 60))}:${pad(Math.abs(minutes) % 60)}`;
}


/** '2026-11-24 22:00 CET' for an ISO time with offset. null for anything else. */
export function local_time_text(iso) {
    const date = new Date(iso);
    if (!iso || Number.isNaN(date.getTime())) {
        return null;
    }
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())} ${zone_name(date)}`;
}


/**
 * The value of <input type="datetime-local"> ('2026-11-24T22:00'), a time of the browser's time zone,
 * as ISO 8601 with its offset ('2026-11-24T22:00:00+01:00'). null if it's not a time.
 */
export function local_input_to_iso(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value || '');
    if (!match) {
        return null;
    }
    const [, y, m, d, h, min] = match.map(Number);
    const date = new Date(y, m - 1, d, h, min);
    if (Number.isNaN(date.getTime())) {
        return null;
    }
    // A time which doesn't exist (the change to daylight saving time) is moved by the browser: its result counts
    return `${to_local_input(date)}:00${offset_text(date)}`;
}


/** A date as value of <input type="datetime-local"> */
export function to_local_input(date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}


/** Shows the <time data-local-time> elements below `root` in the time zone of the browser */
export function localize_times(root = document) {
    const times = root.matches?.('time[data-local-time]') ? [root] : [];
    times.push(...(root.querySelectorAll?.('time[data-local-time]') || []));
    for (const time of times) {
        const text = local_time_text(time.getAttribute('datetime'));
        if (text !== null && time.textContent !== text) {
            time.textContent = text;
            time.title = time.getAttribute('datetime');
        }
    }
}
