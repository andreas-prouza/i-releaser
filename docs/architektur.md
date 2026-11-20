- Platform (web, desktop, CLI): web
- Operation (local, own server, cloud): own server
- Data storage and backup: SQLite DB
- Start:
  - Start script
- Language: Python
- Web framework: FastAPI
- Security has top priority.
  If the software runs on its own server at some point, its security vulnerabilities should be minimized as far as possible.
  Security comes before features, unless it's explicitly decided otherwise.


# Python

Packages have to meet these criteria:
* No security risks
* Widely known
* A GitHub repository has to exist
* The GitHub repository has to have several forks and at least 200 stars

If no package meets the criteria, ask how to proceed.  
Also list which criteria were not met.

Reviewed packages and approved exceptions: see [technik.md](technik.md#package-prüfung).


# GUI

* Navigation bar on the left side
  * It can be collapsed (icons + text vs. icons only)
* Mobile-friendly if possible (low priority)
* Use nice styles
* Use icons for buttons if possible. Icon + text is fine too
* For tables, use `bootstrap-table` with these features:
  * Sorting
  * Filters (dropdown or text input, whichever makes sense)
  * Pagination
* Use HTML templates with a template engine (Jinja2)
* Use `Sweetalert2` for popups and input where it makes sense.  
  E.g. when creating or editing records
* One layout for all pages: `base.html` with its blocks, the page header and the other parts of a page as macros of `templates/components/ui.html` (see [layout](features/web-ui-layout.md))
* Colours, spacing and fonts only from the tokens of `static/assets/css/app.css` (light and dark). Text and status colours have a contrast of at least 4.5 : 1 in both themes (tested)
* A status is shown with the macro `status_pill`; the mapping status → colour, icon and text is only in `web_modules/status_view.py`
* Icons: Bootstrap Icons
* Dark mode follows the browser, with a switch in the navigation. Everything works from 768 px; below 992 px the navigation is a panel over the page
* Scripts only in files (ES modules in `static/assets/js/`, no build step). No inline scripts, no `on...=` attributes, no values inside JavaScript in templates: data comes from `data-*` attributes or a JSON block (see [scripts](features/web-ui-scripts.md#rules)). The Content-Security-Policy of the web app blocks everything else (see [security headers](features/web-ui-security-headers.md))
* No HTML built from data as text, neither in Python nor in JavaScript
* Requests with `app/api.js`, dialogs with `app/dialogs.js`: actions which can't be undone ask once, the result is a toast. Larger content (logs, steps) is part of the page or a panel
* All files local. Libraries pinned and listed in [technik.md](technik.md#package-prüfung)


# Update

* Back up the DB before every update
* Maintain a `CHANGELOG.md`. Do it in a very compact way. Don't put too much details in it. Instead of too much details, link to the related .md file
