# CLAUDE.md

Guide for working on **Profito** – local accounting/time-tracking app.


# i-Releaser


## Way of working

- Each feature has its own file in [docs/features/](docs/features/)
- Each feature has a status (`draft`, `ready`, `finished`)
- Only implement features with status `ready`. For status `draft`, clarify the open questions first, don't guess.
- A feature is done when all acceptance criteria are met and covered by tests. Then set its status to `finished`.
- If something is listed under "Non-goals" or isn't described in any feature, ask whether it should be implemented.
- Add decisions made during the implementation (technology, data model) to the docs.
- [docs/glossar.md](docs/glossar.md) describes the abbreviations
- [docs/architektur.md](docs/architektur.md) contains the guidelines for the implementation
- Suggestions for improvement are explicitly welcome!!
- Hints about possible bugs are explicitly welcome!!


## Documentation

The complete documentation is in [`docs/`](README.md):
functional (use cases), data model (ER), technology (API).
When the behavior changes, update the affected documentation file too.
Use `mermaid` to show processes.

- Technology, package review, security concept, API: [docs/technik.md](docs/technik.md)
- Data model: [docs/datenmodell.md](docs/datenmodell.md)


## Development

- All configuration belongs in `etc/` (templates in `etc/examples/`, only these are checked in)
- Tests: `.venv/bin/pytest` (run `.venv/bin/pip install -r requirements-dev.txt` once before)
- Security check of the dependencies: `.venv/bin/pip-audit -r requirements.txt`
- New packages only according to the criteria in [docs/architektur.md](docs/architektur.md). Add the result to [docs/technik.md](docs/technik.md#package-prüfung)
- Database changes with Alembic migrations? Currently this is solved differently (see [docs/technik.md](docs/technik.md#entwicklung))
