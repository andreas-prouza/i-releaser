# DB deployment: names from custom data are put into CL commands unchecked

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

The tables of a DB deployment are configured in the custom data (`$.db_deployment.tables`).
`check_system_name` only checks that a name isn't empty and has at most 10 characters ([objects.py:67](../../modules/db_deployment/objects.py#L67)).
`split_object_name` (dependents) checks nothing but the `/`.

The names are put into CL commands, e.g.:

* `ALCOBJ OBJ(...)`, `DLCOBJ`, `MOVOBJ`, `CHGPF`, `STRJRNPF`, `GRTOBJAUT`, `CHGOBJOWN` ([cutover.py](../../modules/db_deployment/cutover.py))
* `DSPDBR FILE(...)` ([catalog.py:107](../../modules/db_deployment/catalog.py#L107)), `ENDJRNPF` ([cleanup.py:47](../../modules/db_deployment/cleanup.py#L47))
* library list entries (`library_list`)

A name like `A) X(` changes the parameters of these commands. In SQL the names are quoted correctly (`sql_name`).

The column expressions (`columns`) are SQL by design. Who may set them is handled in [custom data on create](custom-data-on-create-unrestricted.md) and `docs/db-deployment.md#security`.


## Requirements

1. `lib`, `name`, the entries of `library_list` and both parts of `dependents` have to be valid IBM i system names: `^[A-Z$#@][A-Z0-9$#@_.]{0,9}$` (after converting to upper case).
2. The keys of `columns` have to be valid column names of the new table (checked against the catalog in `db-prepare`).
3. Invalid names stop `db-prepare` with a message which names the table and the field.


## Acceptance criteria

- [x] Unit test: `A) X(`, `LIB/X`, `A B`, `"X"`, `1ABC`, an empty name and 11 characters are rejected.
- [x] Unit test: `ORDERS`, `$ORD#1`, `@X_Y.Z`, lower-case names are accepted (and upper-cased).
- [x] Unit test: a column key which doesn't exist in the new table stops `db-prepare`.


## Non-goals

* SQL names longer than 10 characters (quoted SQL names)


## Decisions

* Support long SQL names later? **Not now.**
