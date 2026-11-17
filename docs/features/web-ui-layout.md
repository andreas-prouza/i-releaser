# Layout and styles: base layout, navigation, components

- **Status:** draft
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 2
- **Depends on:** [Static assets](web-ui-static-assets.md)


## Current situation

* `base.html`: a dark sidebar of Bootstrap utility classes, with inline SVG icons. It can't be collapsed. Below 576 px only the icons are shown, but the sidebar stays 180 px wide (version and "Developed by" keep their text).
* The active entry comes from `?sidebar_active=...`, which every link has to carry. Projects are never marked (see [minor defects](../bugfixes/minor-web-defects.md), 6).
* `Configuration` and its page are shown to everyone, the page answers users without `admin` with an error.
* The whole content is inside `<form name="main" method="post">`. Nothing uses the form; pages with own forms end up with a form in a form.
* No page title, no heading area: each page starts with its own mix of `<h1>`, `<h2>`, `<h3>` and a `Back to overview` button.
* Colours are those of Bootstrap's buttons, used for statuses. Own CSS is spread over `global.css` and `<style>` blocks in four templates.
* Login page: a full-width form with controls that do nothing. Error page: see [minor defects](../bugfixes/minor-web-defects.md), 8 – 10.


## Feature

### Base layout

```
+--------------------+----------------------------------------------------------+
| [logo] i-Releaser  |  Deployments / erp / Version 6          <- breadcrumb    |
|                    |  Title                    [action] [action]  <- header   |
| > Deployments      |  meta line                                               |
|   Objects          | -------------------------------------------------------- |
|   Workflows        |                                                          |
|   --------------   |  content                                                 |
|   Settings         |                                                          |
|   Logs           v |                                                          |
|   --------------   |                                                          |
|   BOSS             |                                                          |
|   Log out          |                                                          |
|                    |                                                          |
| [<<] [theme] 3.1.0 |                                                          |
+--------------------+----------------------------------------------------------+
```

* `base.html` keeps its blocks `title`, `css`, `content`, `no_form_content` and `scripts`: custom routes use them. The form around `content` is removed, `no_form_content` stays as a second block below it.
* New blocks: `page_header` (breadcrumb, title, actions) and `nav_active`.
* `<main>` for the content, `<nav>` for the navigation, one `<h1>` per page.
* The banner of the local debugging mode stays, as one line above the header.

### Navigation

* Entries: `Deployments`, `Objects`, `Workflows`; for users with `admin`: `Settings`, `Logs` (with the log files below it); the user (opens the user page), `Log out`; at the bottom the switch to collapse, the theme switch and the version.
* The projects are not in the navigation any more: the deployment list has them (see [lists](web-ui-lists.md)).
* Collapsed: icons only, the text as tooltip. The state is remembered in the browser (`localStorage`).
* Below 992 px the navigation is hidden and opens over the page with a menu button.
* The active entry is set by the page (`nav_active`), not by a parameter. Links don't carry `sidebar_active` any more; old links with it still work.
* `Developed by` moves to the login page and the user page.

### Page header

A macro `page_header(title, breadcrumb, meta)` with a block for actions:

* Breadcrumb for pages below a list (`Deployments / erp / Version 6`). It replaces `Back to overview`.
* `<title>` of the tab: `<page> · i-Releaser`, for a deployment `erp 6 · failed · i-Releaser`.

### Styles

* `static/assets/css/app.css` replaces `global.css` and the `<style>` blocks, page by page.
* Design tokens as CSS variables (`--ir-...`), defined for light and dark:
  * Surfaces, borders, text, muted text, link, focus
  * One colour per status kind: `neutral` (new), `ready`, `running` (in process, in preparation, queued), `success` (finished), `danger` (failed), `canceled`
  * Spacing steps, radius, the font stacks (system fonts; monospace for commands, logs, libraries and ids)
* Bootstrap's variables are set from these tokens, so its components and bootstrap-table follow.
* Dark mode: `data-bs-theme` on `<html>`, from the setting of the browser, or from the switch (remembered in `localStorage`). A small script file in `<head>` sets it before the page is drawn.
* Text and status colours have a contrast of at least 4.5 : 1 in both themes.

### Components

Macros in `templates/components/`, with their classes in `app.css`:

| Component | Use |
|---|---|
| `status_pill(status)` | Every status of deployments, stages, steps, objects and jobs: colour, icon and text. Not a button. Unknown values are shown neutral. |
| `icon_button(icon, label, ...)` | Button with only an icon: a real `<button>` with `aria-label` and tooltip |
| `kv_list` | Key and value pairs (details of a deployment or stage) instead of tables |
| `section(title, ...)` | A titled part of a page, with optional actions on the right |
| `empty_state(text)` | "No deployments yet", "This deployment has no objects" |
| `code_block(text, language)` | Commands, JSON, paths: monospace, with a copy button |
| Switch | Bootstrap's `form-switch` replaces the own `.switch` / `.slider` CSS |

* One mapping status → kind, icon and text in Python (`web_modules/status_view.py`), used by `status_pill`. The seven copies of `btn_classes` disappear with their pages.
* Template filters: `datetime` (`2026-11-16 18:56:47`), `duration` (`1.2 s`, `3 min 10 s`), `or_dash` (`–` instead of `None`).

### Login and error page

* Login: a centred card with the logo, user, password and `Log in`. The error message above the fields. The fields have `autocomplete="username"` / `current-password`, the user field has the focus. No navigation. The limits of the login form stay ([technik.md](../technik.md#known-vulnerabilities)).
* Error: status code, the message, for unexpected errors the error id, and a link back to the deployments. With navigation only for logged-in users.

### Order

Pages which are not redesigned yet are shown in the new layout with their old content and scripts. Each later step moves its page to the components.


## Acceptance criteria

- [ ] Test: every page has a `<title>` with its name, and exactly one `<h1>`.
- [ ] Test: the active entry of each page, without `sidebar_active`: list, deployment (→ `Deployments`), objects, workflows, settings, a log, user.
- [ ] Test: `Settings` and `Logs` are only in the navigation of users with `admin`.
- [ ] Test: no template has a form inside a form; `base.html` has no form.
- [ ] Test: the login page has only user, password and the button, and no navigation. The tests of the login still pass.
- [ ] Test: the error page for an unknown deployment has status 404, the message, and no other text of the old page.
- [ ] Test: `status_pill` for every value of the status classes (`Meta_file_status`, stage, step, object, job) has a text and an icon; an unknown value doesn't fail.
- [ ] Test: the filters `datetime`, `duration`, `or_dash`.
- [ ] Test: custom route with a template which extends `base.html` and fills `content` and `scripts` still works.
- [ ] Looked at in Chrome with test data, light and dark, at 1440 px, 1024 px and 768 px: no horizontal scrolling, navigation collapsed and open. With [browser tests](web-ui-browser-tests.md): the collapsed state and the theme survive a reload.
- [ ] Docs: [scripts.md](../scripts.md) (blocks of `base.html` for custom routes), [architektur.md](../architektur.md#gui).


## Non-goals

* The content of the pages: steps 4 and 6 – 8
* A settings page for the theme or other options per user on the server


## Open questions

1. Questions 1 – 6 of the [modernization](web-ui-modernization.md#open-questions) (Bootstrap, mockup, dark mode, look, logo, small screens).
2. Names in the navigation: `Configuration` → `Settings`, `Object list` → `Objects`. OK?
3. Projects: today a sub-menu of the navigation and buttons above the list. Proposal: only in the deployment list. Or keep them in the navigation as well?
