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


# Update

* Back up the DB before every update
* Maintain a `CHANGELOG.md`. Do it in a very compact way. Don't put too much details in it. Instead of too much details, link to the related .md file
