/*
 * Requests to the Web API of the web app (docs/features/web-ui-scripts.md).
 *
 *     import { get_json, post_json } from '/static/assets/js/app/api.js';
 *     const data = await post_json(`/api/run_stage/${id}/${stage}/continue`);
 *
 * A response with an error status throws an Api_Error with the message of the server
 * (docs/webapi.md#responses-and-errors). An ended session (401) shows "Your session has ended" once.
 * An action which needs a recent code of the authenticator app (403 with `step_up`) asks for it and is sent again.
 */
import { ask_code, session_ended } from './dialogs.js';


export class Api_Error extends Error {
    constructor(message, status = 0, data = null) {
        super(message);
        this.name = 'Api_Error';
        this.status = status;
        this.data = data;
    }
}


function message_of(data) {
    if (data && typeof data === 'object' && 'message' in data) {
        return typeof data.message === 'string' ? data.message : JSON.stringify(data.message);
    }
    return typeof data === 'string' && data.length < 300 ? data : '';
}


async function request(method, url, data, html = false, background = false, confirmed = false) {

    // X-Requested-With: the web app answers errors with JSON, also for parts of pages (webmiddleware.wants_html)
    const options = {method, credentials: 'same-origin', cache: 'no-store',
                     headers: {'Accept': html ? 'text/html' : 'application/json', 'X-Requested-With': 'fetch'}};
    // Requests of the page itself (live updates), not of the user: they don't extend the session (server_sessions.py)
    if (background) {
        options.headers['X-Background'] = '1';
    }
    if (data !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(data);
    }

    let response;
    try {
        response = await fetch(url, options);
    } catch {
        throw new Api_Error("The web app can't be reached. Check the connection and try again.");
    }

    const text = await response.text();
    if (html && response.ok) {
        return text;
    }

    let body = null;
    try {
        body = text ? JSON.parse(text) : null;
    } catch {
        body = text;
    }

    if (response.status === 401) {
        session_ended();
        throw new Api_Error('Your session has ended', 401, body);
    }

    // The action needs a recent code of the authenticator app (step-up): ask for it and send the request again, once.
    // In an open dialog (confirm_action) the dialog asks: a second dialog would close it.
    if (response.status === 403 && body?.step_up && !confirmed && !Swal.isVisible()) {
        const verified = await ask_code({verify: verify_code});
        if (verified) {
            return request(method, url, data, html, background, true);
        }
        throw new Api_Error('Not confirmed with the code of the authenticator app', 403, body);
    }

    if (!response.ok) {
        throw new Api_Error(message_of(body) || `${response.status} ${response.statusText}`, response.status, body);
    }

    return body;
}


export function get_json(url) {
    return request('GET', url);
}


export function post_json(url, data = {}) {
    return request('POST', url, data);
}


/** DELETE of a resource of the Web API v2 (answer 204: null) */
export function delete_json(url) {
    return request('DELETE', url);
}


/** Confirms the code of the authenticator app for actions which need a recent one (step-up) */
export function verify_code(code) {
    return request('POST', '/api/mfa/verify', {code}, false, false, true);
}


/**
 * A part of a page, rendered by the server (e.g. the steps of a stage). Errors like get_json.
 * background: loaded by the page itself (live updates), not by the user
 */
export function get_html(url, {background = false} = {}) {
    return request('GET', url, undefined, true, background);
}
