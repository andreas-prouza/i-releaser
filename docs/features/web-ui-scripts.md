# Scripts in files: modules, shared helpers, rules

- **Status:** draft
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 3
- **Depends on:** [Layout and styles](web-ui-layout.md)


## Current situation

* 1,528 lines of JavaScript are inside templates, mixed with Jinja2 (`{{ flow_javascript|safe }}`, `{{ workflows|tojson }}`, `'{{ deployment_dict['general']['id'] }}'`). They can't be checked, tested or cached, and a Content-Security-Policy can't allow them without allowing every inline script.
* 49 inline handlers call global functions with values written into the call. This is the cause of [values run as script](../bugfixes/web-values-run-as-script.md).
* `web.deploy.js` contains the same `fetch` call five times (`http_getData`, `http_get`, `http_post`, `postData`, `async_postData`). The callers handle errors each in their own way: some check `data['status']`, some `response.ok`, some nothing.
* `Swal.mixin({...})` with the same options is repeated in seven functions. An action shows up to three dialogs.
* If the session has ended, an action shows `You are not logged in` as error, and the auto refresh stops without a message.
* 48 `console.log` lines.


## Feature

### Files

```
static/assets/js/
  app/api.js        get_json(url), post_json(url, data)
  app/dialogs.js    confirm_action(...), choose(...), show_error(...), toast(...)
  app/dom.js        on_action(name, handler), read_json(id), escape_html(text)
  app/tables.js     defaults of bootstrap-table
  app/theme.js      theme and navigation (from step 2)
  pages/<page>.js   one file per page
  web.deploy.js     old global functions, kept for custom templates (deprecated)
```

* ES modules (`<script type="module" src="...">`), no build step, no new package. The libraries stay normal scripts, loaded by `base.html`.
* `api.js`: one `fetch`. A response with an error status throws an error with the `message` of the server (see [Web API](../webapi.md#responses-and-errors)). Status `401` shows `Your session has ended` with a button to the login page.
* `dialogs.js` (SweetAlert2):
  * `confirm_action`: for actions which can't be undone. The buttons are named after the action (`Cancel deployment` / `Keep it`), no `Are you sure?` / `No, ups!`.
  * The result of an action is a `toast` (a short message which disappears), not a second dialog. An error stays until it's closed.
  * A canceled dialog shows nothing.
* `tables.js`: page sizes, texts, Bootstrap Icons, and `escape` turned on, for all tables.

### Rules

1. Templates contain no script code. Allowed: `<script src>` and data blocks `<script type="application/json">`.
2. No `on...=` attributes, no `javascript:` URLs.
3. A script gets data of the server from `data-*` attributes or a JSON block, never as generated JavaScript:

   ```html
   <button class="btn btn-primary" data-action="run-stage"
           data-stage-id="{{ stage.id }}" data-stage-name="{{ stage.name }}">Run stage</button>
   <script type="application/json" id="page-data">{{ page_data|tojson }}</script>
   ```

   ```js
   on_action('run-stage', (button) => run_stage(button.dataset.stageId, button.dataset.stageName));
   const data = read_json('page-data');
   ```

4. JavaScript doesn't build HTML from data as text. It uses the DOM API (`textContent`), or asks the server for a rendered part of a page.
5. Python doesn't build HTML or JavaScript as text.
6. No `console.log`. Errors are shown to the user.

A test checks the rules for all templates and own scripts. Templates which are not moved yet are a list in the test (`LEGACY_TEMPLATES`); the test fails if a template of the list already follows the rules, so the list shrinks with each step. It's empty before [step 9](web-ui-security-headers.md).

### Custom templates

`custom_templates/deployment_status.html` and the pages of `custom/routes` are affected by rules 1 and 2 as soon as the Content-Security-Policy is active (step 9).

* Scripts of custom templates are files in `webapp/static/custom/` (kept by updates, like `webapp/custom/`), loaded by the custom template with `<script type="module" src="{{ url_for('static', path='custom/...js') }}">`.
* They can import the helpers (`import { post_json } from '../assets/js/app/api.js'`), which are documented in [scripts.md](../scripts.md). `Swal` stays global.
* `postData`, `http_post`, `http_get` and `http_getData` stay as global functions in `web.deploy.js` until the next major version.
* The context of `deployment_status.html` is documented: `deployment_dict` and where it's shown (see [deployment page](web-ui-deployment-page.md#header)).
* [scripts.md](../scripts.md) gets the rollback button as example in the new form (template and script file).
* Until step 9 old custom templates keep working unchanged.


## Acceptance criteria

- [ ] Test: the rules 1, 2 and 6 for all templates outside `LEGACY_TEMPLATES` and all own scripts; the list contains no template which follows the rules.
- [ ] Test: own scripts use `innerHTML`, `insertAdjacentHTML` or `document.write` only where a list in the test allows it (rendered parts from the server).
- [ ] Test: Python code of the web app contains no HTML tags in strings (`flowchart.py` is on the list until step 4).
- [ ] Test: a custom template with a script file in `static/custom/` is rendered and its file is delivered.
- [ ] Browser test (or manual check, see [browser tests](web-ui-browser-tests.md)): an error of the server is shown with its message; an ended session shows `Your session has ended`; a confirmed action shows one dialog and one toast.
- [ ] Docs: [scripts.md](../scripts.md#web-app-extensions) (custom templates, helpers), [installation.md](../installation.md) (`webapp/static/custom/` is kept by updates), [architektur.md](../architektur.md#gui).


## Non-goals

* TypeScript, a bundler, or a JavaScript test runner
* Replacing jQuery: bootstrap-table needs it. Own scripts don't use it, except to call bootstrap-table.


## Open questions

1. Custom templates: scripts as files in `webapp/static/custom/` (**recommended**: the policy stays strict, no exception), or inline scripts with a nonce (`<script nonce="{{ csp_nonce }}">`: custom templates stay one file, but every page gets a policy with a nonce and inline `onclick` still doesn't work)?
2. How long do the old global functions (`postData`, ...) stay: until the next major version (**recommended**) or removed with step 9?
