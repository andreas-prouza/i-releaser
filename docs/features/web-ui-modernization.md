# Modernization of the web front end

- **Status:** finished (2026-11-20; all steps finished and tested, not on IBM i. Open: the run of the browser tests on GitHub, see [browser tests](web-ui-browser-tests.md))
- **Type:** improvement
- **Priority:** P2
- **Source:** User request 2026-11-16 (like the UI refresh of the OBI extension)

Analysis of the web front end, the answer to "complete redesign?", and the plan. Each step has its own file, see [steps](#steps).


## Result in short

* **Yes, a redesign of the front end:** new layout, new styles, every page laid out again, scripts moved out of the templates. Step by step, the app stays usable after each step (as in the OBI extension).
* **No rewrite of the technology:** the pages stay Jinja2 templates rendered by FastAPI. No single-page app, no Node build.
  * The problems below don't come from server rendering. They come from scripts, styles and HTML which grew inside the templates.
  * A single-page app (as tried in `react-ireleaser`, Next.js, last change 2025-02) needs a build chain with Node, many new packages to review, and login, permissions and every page a second time. [architektur.md](../architektur.md) asks for Jinja2 templates, and i-Releaser has to be installable on IBM i with Python only.
* **The server stays as it is.** The Web API and the URLs used from outside don't change (the OBI extension uses `/api/...` and `/show_details/{id}`). A few additions are listed in the steps.
* **Six defects were found on the way,** three of them should be fixed before the redesign, see [defects](#defects-found).


## How it was analysed

* All templates, scripts, styles, routes and the middleware were read.
* The web app was run on a copy with test data (`tests/web_server.py`: three workflows, a failed deployment with objects, parallel stages) and opened in Chrome: every page at 1440 px, the deployment page and the list at 420 px.
* Suspected defects were reproduced there. "Code review" marks what was only found in the code.


## Current situation

| Area | Finding |
|---|---|
| Scripts | 1,528 lines of JavaScript inside 6 templates (866 in `show-deployment.html`, 478 in `settings.html`). 49 inline handlers (`onclick="..."`): 43 in templates, 6 in Python strings. Python builds HTML and JavaScript as text (`flowchart.py`), JavaScript builds HTML as text. `web.deploy.js` has five copies of the same `fetch` call. |
| Styles | 276 lines of CSS inside templates. Layout with nested tables (up to 4 levels on the permissions page), `&nbsp;` and `<br>` (on 45 lines). |
| Files | `webapp/static` has 35 MB, most of it unused: Font Awesome 22 MB for 3 icons, 2.6 MB of fonts, `rist.css` with 11,335 lines, 3 more stylesheets, 2 scripts, 4 images. See [static assets](web-ui-static-assets.md). |
| Libraries | Loaded in three ways (local, CDN, a redirecting dead CDN). bootstrap-table in two versions, jQuery and Popper twice, SweetAlert2 twice on some pages. Three kinds of icons: Bootstrap Icons, Font Awesome, 6 PNG files used as buttons. |
| Status | A status is a coloured button. Some do something hidden (the status of a deployment reloads the page; the status in the list is the only link to the deployment), most do nothing. The mapping status → colour exists 7 times. |
| Navigation | Not collapsible ([architektur.md](../architektur.md#gui) asks for it). The active entry comes from the parameter `?sidebar_active=`, the project of the list from the session: a URL can't be shared. Detail pages have a `Back to overview` button. No page titles. |
| Deployment page | The steps of a stage are a popup with nested tables, wider than the screen. A log replaces the popup, which is opened again afterwards. Actions need 2 – 3 dialogs (`Are you sure?` → `Canceled!` → reload). Small PNG icons without text start, reset and cancel. |
| Auto refresh | Every change reloads the whole page: filters, the page of the table, the scroll position and opened details are lost. After a connection error it stops for good. |
| Tables | Column names of the database as headings (`meta_file_id`, `latest_create_time`). Jobs, history, steps and keys are plain tables ([architektur.md](../architektur.md#gui): bootstrap-table with sorting, filters, paging). |
| Texts | English with German words (`Projekt`), `None` for empty values, times with microseconds, `No, ups!`. |
| Small screens | Not usable at 420 px. At 1440 px the deployment page is 254 px wider than the window. |
| Dark mode | None. |
| Security | No Content-Security-Policy and no other security headers. See also [defects](#defects-found). |
| Tests | No test runs JavaScript. All defects below were only visible in a browser. |
| Customising | `custom_templates/deployment_status.html` and `custom/routes` depend on the block names of `base.html`, on global functions (`postData`, `Swal`) and on paths of images. Nothing of that is documented as a contract. |


## Defects found

| Priority | Defect | Type | Fix |
|---|---|---|---|
| P1 | [Scripts from third-party servers](../bugfixes/web-scripts-from-third-party-servers.md) | security | finished 2026-11-17 |
| P1 | [Values can run as script (XSS)](../bugfixes/web-values-run-as-script.md) | security | finished 2026-11-17 |
| P1 | [Permissions page: can't save, or removes permissions](../bugfixes/permissions-page-names-in-selectors.md) | bug (data loss) | finished 2026-11-17 |
| P2 | [A stage name can turn off all buttons of the deployment page](../bugfixes/stage-name-breaks-deployment-page.md) | bug | finished 2026-11-17 |
| P2 | [Objects table of the deployment page](../bugfixes/deployment-objects-table.md) | bug | finished 2026-11-19 |
| P3 | [Minor defects of the web pages](../bugfixes/minor-web-defects.md) | bug | finished 2026-11-20 |


## Target

1. **Templates:** one base layout; repeated parts are macros (status, page header, icon button, empty state). No tables for layout.
2. **Styles:** one stylesheet of the app with design tokens (CSS variables) for colours, spacing and fonts, light and dark, on top of Bootstrap 5.3.
3. **Icons:** one set (Bootstrap Icons).
4. **Scripts:** only in files (`static/assets/js/`, ES modules, no build step). Data for a script comes from `data-*` attributes or a JSON block. No inline scripts, no `on...=`.
5. **Files:** everything local, each library once, with a fixed version.
6. **Content-Security-Policy:** makes 4 and 5 a rule the browser enforces.
7. **Status:** shown the same way everywhere, with colour, icon and text. One mapping.
8. **Actions:** the main action of a page is a button with text. Actions which can't be undone ask once. The result is a short message, not a second dialog.
9. **Updates in place:** a change updates the parts of the page it affects.
10. **Tables:** bootstrap-table with sorting, filters and paging for lists; lists of key and value for details.
11. **URLs:** a URL describes the page. The navigation knows the active entry without a parameter.
12. **Customising:** `custom_templates` and `custom/routes` keep working, with a documented contract.


## Steps

```mermaid
flowchart LR
    B[Bugfixes P1] --> S1[1 Static assets]
    S1 --> S2[2 Layout and styles]
    S2 --> S3[3 Scripts]
    S3 --> S4[4 Deployment page]
    S4 --> S5[5 Live updates]
    S3 --> S6[6 Lists]
    S3 --> S7[7 Permissions page]
    S3 --> S8[8 Admin pages]
    S5 --> S9[9 Security headers]
    S6 --> S9
    S7 --> S9
    S8 --> S9
    T[Browser tests] -.-> S3
```

| Step | File | Size | Status |
|---|---|---|---|
| – | The three P1 bugfixes above | S each | finished |
| 1 | [Static assets: local, pinned, cleaned up](web-ui-static-assets.md) | S | finished |
| 2 | [Layout and styles](web-ui-layout.md): base layout, navigation, design tokens, components, login and error page | L | finished |
| 3 | [Scripts in files](web-ui-scripts.md): modules, shared helpers, rules, contract for custom templates | M | finished |
| 4 | [Deployment page](web-ui-deployment-page.md): header, stage flow, steps, objects, logs | L | finished |
| 5 | [Live updates](web-ui-live-updates.md): no reload of the page | M | finished |
| 6 | [Lists](web-ui-lists.md): deployments, objects, start of a workflow | M | finished |
| 7 | [Permissions page](web-ui-permissions-page.md) | M | finished |
| 8 | [Admin pages](web-ui-admin-pages.md): settings, logs, workflows, user | M | finished |
| 9 | [Security headers](web-ui-security-headers.md): Content-Security-Policy | S | finished |
| – | [Browser tests](web-ui-browser-tests.md) (new package) | M | ready (only the run on GitHub is missing) |

Steps 4, 6, 7 and 8 are independent of each other. During the work, pages which were not done yet kept working in the new layout, with their old scripts (removed with step 9, decision 10). All steps are on the branch `redesign` and released together (decision 8).


## Done when

- [x] All steps are `finished`.
- [x] The screenshots of [README.md](../../README.md) are new: `.venv/bin/python tests/screenshots.py` (see [technik.md](../technik.md#tests)).
- [x] [architektur.md](../architektur.md#gui) contains the decisions of this file (see below).
- [x] Changelog entry, with what owners of custom templates have to do before the update.


## Changes of architektur.md

Done (2026-11-20). The section `GUI` got these rules (the earlier rules stay):

* Scripts only in files. No inline scripts, no `on...=` attributes, no values inside JavaScript in templates.
* No HTML built from data as text, neither in Python nor in JavaScript.
* All files local. Libraries pinned and listed in [technik.md](../technik.md#package-prüfung).
* Colours, spacing and fonts only from the tokens of `app.css`. A status is shown with the macro `status_pill`.
* Icons: Bootstrap Icons.
* SweetAlert2 for confirmations and small inputs. Larger content (logs, steps) is part of the page or a panel.


## Non-goals

* A single-page app or another template engine
* Changes of the Web API for other clients, of the database, or of the processing of stages
* Translations: the web app stays English
* New functions (dashboard, statistics, notifications). Ideas which came up are listed in the steps under `Non-goals`.


## Decisions (2026-11-19)

1. **Bootstrap:** Bootstrap 5.3 stays the base; the own stylesheet with design tokens goes on top.
2. **Mockup first:** a mockup of the deployment page and the deployment list, light and dark, is approved before step 2 starts.
3. **Dark mode:** yes. It follows the setting of the browser, with a switch in the navigation (remembered per browser).
4. **Browser tests:** Playwright for Python as development package (see [browser tests](web-ui-browser-tests.md)).
5. **Logo:** `logo2-icon.png` (the first image of [README.md](../../README.md)). `logo.png` is the logo of the developer and only stays next to "Developed by".
6. **Small screens:** everything works from 768 px. Below that the navigation becomes a menu and wide tables scroll inside their box; nothing is optimised further.
7. **Custom templates:** with the Content-Security-Policy (step 9) inline scripts and `on...=` in custom templates stop working. Accepted, with a migration note in the changelog, an example in [scripts.md](../scripts.md#web-app-extensions) and `C_CSP_REPORT_ONLY` for a transition period (see [scripts](web-ui-scripts.md#custom-templates)).
8. **Release:** all steps on one branch (`redesign`), merged and released together. The steps are still done and finished one after the other.
9. **Look:** the same language as the i-Releaser card of the OBI extension (status pills, stepper with circles, attention bar). The [mockup](https://claude.ai/artifact/HQqeugdfJgXrLDZLn2tRX7) (deployment page linear and with parallel stages, deployment list, light and dark) is approved as it is.
10. **Old script functions:** `postData`, `http_post`, ... are removed with step 9 (see [scripts](web-ui-scripts.md#decisions-2026-11-19)).


## Open questions

None.
