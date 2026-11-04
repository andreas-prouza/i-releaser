"""
DB deployment: deploys changes of large tables with a minimal downtime

The new table is built in a shadow library and filled while the users keep working.
Changes made in the meantime are taken from the journal and applied to the new table.
At the cut-over only the last changes are applied, then the new table replaces the old one.

Like Rapid Fire (https://rdi-open-source.github.io/), changes are tracked by relative record number (RRN):
the journal only tells which rows have changed, their current content is read from the table again.

See docs/db-deployment.md
"""
