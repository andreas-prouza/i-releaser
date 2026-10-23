# DB deployment

Deploys changes of large tables (millions or billions of rows) with a downtime of minutes.

A normal deployment changes a table in place (`CHGPF`, `ALTER TABLE`, `CREATE OR REPLACE TABLE`).
The table is locked for the whole conversion, which can take hours.

The DB deployment builds the new table in a shadow library and fills it while the users keep working.
The changes they make meanwhile are taken from the journal and applied to the new table.
In the maintenance window only the last changes are applied, then the new table replaces the old one.

The idea comes from [Rapid Fire](https://rdi-open-source.github.io/), but it's implemented in Python and SQL: no RPG programs are generated.


## How it works

```
        days before the release                          maintenance window
  ┌──────────────────────────────────────────┐   ┌───────────────────────────────────┐
  db-prepare            db-copy                  db-cutover                 db-cleanup
  shadow library        copy the rows            catch up                   end journaling
  new table + indexes   (users keep working)     lock (ALCOBJ *EXCL)        delete shadow
  start journaling      catch up with changes    apply the last changes     library
                                                 swap old <-> new table
                                                 unlock
```

* **Rows are tracked by relative record number (RRN).** The journal only tells which rows have changed. Their current content is read from the old table again.
  * So any journal setting works (`IMAGES(*AFTER)`, minimized entry data, LOBs).
  * Tables without a unique key are supported.
* **A map table relates the RRN of each row in the old table to its RRN in the new table.** The new table doesn't reuse deleted records (`REUSEDLT(*NO)`) while it is filled, so each inserted row gets the next RRN. Each insert is verified.
* **The copy runs without locks.** Changes during the copy are applied afterwards from the journal.
* **Rows which can't be applied are recorded and tried again later.**
  * A duplicate key may exist only for a while, as the rows are applied in RRN order. It's resolved by a later change.
  * Permanent problems block the cut-over: old data which violates a new unique key, or a column expression which fails for a row.
* **The state lives on the target system** in the shadow library, so every step can be run again: it continues where it has stopped.
  * The copy continues after the last completed part.
  * The cut-over continues the swap of the objects.

The cut-over:

1. Catch up with the changes while the users still work.
2. Lock the old table and its dependent files exclusively: `ALCOBJ … CONFLICT(*RQSRLS)`, which also asks jobs with pseudo-closed cursors to release them.
3. Apply the remaining changes and compare the number of rows of the old table, the new table and the map table.
4. Finish the new table:
   * `REUSEDLT` as defined by its source;
   * identity columns restarted after the highest value;
   * journaled to the journal of the old table, with the same `IMAGES`/`OMTJRNE`;
   * authorities of the old files (`GRTOBJAUT REFOBJ`).
5. Swap: the old table and its dependent files are moved to the backup library of the deployment (`b000000123`). The new ones are moved from the shadow library to production.
6. Create the views over the table again (`CREATE OR REPLACE` from the SQL generated in `db-prepare`). Give the new files the owners of the old ones.
7. Release the locks.

If moving an object fails, the objects moved so far are moved back.


## Requirements and limitations

* i-Releaser connects to Db2 for i of the target system via ODBC (`pyodbc`, IBM i Access ODBC Driver). It's the same driver as for the login.
* The new table and its logical files and indexes are built from their sources of the deployment (OBI flow).
  * The source has to be available to the target system, so the target is the system i-Releaser runs on (as for `obi.py`).
  * SQL sources are run with `NAMING(*SQL)` and the shadow library as default schema.
  * Qualified references to the table (`PRODLIB.ORDERS`, `PRODLIB/ORDERS`) are pointed to the shadow library.
  * `SET SCHEMA` is not allowed.
  * DDS logical files have to reference the physical file unqualified (`PFILE(ORDERS)`).
* Files which depend on the table:
  * SQL indexes which are not part of the deployment are built from their generated SQL (`QSYS2.GENERATE_SQL`).
  * DDS logical files which are not part of the deployment are built from the source member they have been created from.
  * Views are created again after the swap.
  * Views which are part of the deployment are created by the deployment as usual.
* Not supported yet:
  * Triggers and foreign keys (of the table, or referencing it). Remove them before and add them after the deployment with your own steps.
  * Files with more than one member.
  * Libraries in different ASPs.
* The table must not be reorganized (`RGZPFM`), initialized, altered or have its journaling ended until the cut-over. If that happens, the table has to be prepared and copied again. Clearing it (`CLRPFM`) is supported.
* Receivers of the journal must not be deleted until the cut-over.
  * If the table isn't journaled yet, `db-prepare` creates a journal in the shadow library (`MNGRCV(*SYSTEM) DLTRCV(*NO)`).
  * Don't reset the sequence numbers (`CHGJRN SEQOPT(*RESET)`) during the DB deployment.
* The new table keeps `SIZE(*NOMAX)`.
* Generated columns other than identity columns (e.g. row change timestamps) get new values, unless they have an expression.


## Check your system first

`docs/db-deployment-spike.py` checks on your IBM i that the assumptions of the DB deployment hold. Run it once before the first deployment and after OS upgrades.

It creates two test libraries and deletes them again:

```bash
.venv/bin/python docs/db-deployment-spike.py --host localhost --lib IRSPIKE --rows 1000000
```

It checks:

* the catalog queries;
* direct RRN access: `RRN(T) BETWEEN`, `=` and `IN (...)` must be much faster than a table scan;
* that the insert order is kept;
* the `UPDATE`/`DELETE` statements by RRN;
* `DISPLAY_JOURNAL`;
* `STRJRNPF` while the table is in use;
* `ALCOBJ` over ODBC, and `MOVOBJ` of a locked file;
* `GENERATE_SQL`.

Every check must show `PASS` or `INFO`.


## Set up

1. Copy `scripts/examples/db_deployment.py` to `scripts/`. Restart the web app, and the processing service if you use it.

2. Create `etc/db_deployment.json` (see `etc/examples/db_deployment.json`). Connections are found by the `host` of the stage:

   ```json
   {
     "connections": {
       "localhost": {"system": "localhost", "user": "*CURRENT", "password": "*CURRENT"},
       "prod400":   {"system": "prod400.example.com", "user": "IRELEASER", "password_env": "I_RELEASER_DB_PROD400_PASSWORD"}
     },
     "defaults": {"batch_size": 50000, "lock_wait_seconds": 60}
   }
   ```

   | Connection key | Description |
   |---|---|
   | `system` | Host name of the IBM i (default: the key) |
   | `user`, `password` | User profile and password |
   | `password_env` | Name of an environment variable with the password, instead of `password` |
   | `driver` | ODBC driver (default: `IBM i Access ODBC Driver`) |
   | `options` | More keywords of the connection string |

   The user needs authority to:
   * create libraries;
   * create, move and change the tables and their files;
   * journal them;
   * read their journal;
   * grant authorities.

3. Add the steps to `etc/default_step_action.json` or the `step_action` of your workflow (see `etc/examples/default_step_action.json`):

   ```json
   {"processing_step": "db-prepare", "environment": "SCRIPT", "execute": "db_deployment.prepare_tables", "check_error": true},
   {"processing_step": "db-copy", "environment": "SCRIPT", "execute": "db_deployment.copy_tables", "check_error": true},
   {"processing_step": "db-cutover", "environment": "SCRIPT", "execute": "db_deployment.cutover_tables", "check_error": true},
   {"processing_step": "db-cleanup", "environment": "SCRIPT", "execute": "db_deployment.cleanup_tables", "check_error": true}
   ```

4. Use them in the workflow:
   * `db-prepare` and `db-copy` go into their own stage, after the object list has been loaded.
   * `db-cutover` goes into the deployment stage, before the objects are deployed. Programs with the new record format are then deployed right after the new table, so there are no level checks.

   ```json
   {
     "name": "DB prepare + copy",
     "next_stages": ["Backup old objects"],
     "host": "localhost",
     "processing_steps": ["db-prepare", "db-copy"],
     "execute_remote": false
   },
   ...
   {
     "name": "DEPLOY",
     "next_stages": ["END"],
     "host": "localhost",
     "processing_steps": ["pre", "db-cutover", "perform-deployment", "db-cleanup", "post"],
     "execute_remote": false
   }
   ```

   Add `"$.db_deployment"` to the `editable_fields` of the workflow, so the tables can be configured in the web app.

5. Your deployment step has to skip the objects which are replaced by the cut-over. Check each object:

   ```python
   from modules.db_deployment import objects as db_objects

   if db_objects.check_deploy_object(meta_file, obj):
       continue    # replaced by the cut-over
   ```

   `check_deploy_object` raises an error if the object belongs to the DB deployment but the cut-over hasn't been done yet. This avoids that a large table is changed in place by accident.

   Done in:
   * `scripts/obi.py` (`perform_deployment`);
   * `scripts/examples/backup_old_objects.py`, which doesn't save these tables: the old table is kept in the backup library by the cut-over.

6. Use the [processing service](processing-service.md) (`C_PROCESSING_MODE = 'service'`). The copy of a large table takes hours, and the service keeps it running when the web app restarts. If a run ends anyway, run the stage again: the copy continues where it has stopped.


## Configure the tables of a deployment

In the custom data of the deployment:

```json
{
  "db_deployment": {
    "tables": [
      {
        "lib": "PRODLIB",
        "name": "ORDERS",
        "columns": {
          "ORDDAT": "DATE(TIMESTAMP_FORMAT(DIGITS(ORDDT8), 'YYYYMMDD'))",
          "STATUS": "CASE WHEN STS = 'X' THEN 'C' ELSE STS END",
          "NEWCOL": "'N'"
        },
        "dependents": ["PRODLIB/ORDERS9"],
        "library_list": ["REFLIB"],
        "batch_size": 100000
      }
    ]
  }
}
```

| Key | Description |
|---|---|
| `lib`, `name` | System name of the table in production. It has to be part of the deployment (attribute `sqltable` or `pf`). |
| `columns` | SQL expressions over the columns of the old table, for columns of the new table. See below. |
| `dependents` | New logical files or indexes of the deployment over this table (`LIB/NAME`). They are built in the shadow library too, so they don't have to be built over the large table in the maintenance window. Existing dependent files are found automatically. |
| `library_list` | Libraries added to the library list while building the new files (e.g. for field reference files) |
| `batch_size`, ... | Settings of this table, see below |

How the columns are filled:

* A column with the same name gets the value of the old column. Db2 converts it (length, precision, CCSID, ...).
* A new column without an expression gets its default value. If it is `NOT NULL` without a default, it needs an expression.
* A column with an expression gets the result of the expression. Write the columns of the old table without a qualifier.
* `"*DEFAULT"` as expression gives a column its default value.
* Columns which don't exist in the new table are dropped.

`db-prepare` converts the first 1000 rows to check the expressions, and logs the mapping of all columns.

Don't change the order of the tables once `db-prepare` has run: the state of a table is stored by its position.
A changed `columns`, `dependents` or `library_list` makes `db-prepare` prepare the table again. Settings can be changed at any time.

### Settings

In `defaults` of `etc/db_deployment.json`, or per table:

| Setting | Default | Description |
|---|---|---|
| `batch_size` | 50000 | Rows per statement of the copy |
| `apply_batch_size` | 1000 | Changed rows per statement when applying the journal changes |
| `journal_batch_size` | 50000 | Journal entries per read |
| `catch_up_threshold` | 1000 | Catching up ends when no more than this number of changed rows wait |
| `catch_up_max_cycles` | 100 | Catching up ends after this number of cycles anyway (changes may come in faster than they are applied) |
| `lock_wait_seconds` | 60 | Wait time for the exclusive lock of the cut-over |
| `progress_interval_seconds` | 60 | Seconds between two progress messages in the log |
| `verify_inserts` | true | Compare inserted rows with the source to make sure they got the expected RRN. Switch it off for tables with field procedures. |
| `max_errors` | 1000 | A step ends if more rows than this can't be applied (e.g. a wrong column expression) |


## Run it

| Step | When | Run again |
|---|---|---|
| `db-prepare` | Some days before the release | Nothing to do for a prepared table. A failed table (e.g. reorganized meanwhile) is prepared again from scratch. |
| `db-copy` | Right after it. Logs its progress (records/s, remaining time) every minute. | Continues the copy, then catches up |
| `db-cutover` | In the maintenance window, before the programs are deployed | Continues where it has stopped |
| `db-cleanup` | After the deployment, or to give the DB deployment up | Deletes the shadow library. Ends the journaling i-Releaser has started. |

The users can work until the cut-over.
The longer the time between `db-copy` and `db-cutover`, the more changes the cut-over has to catch up with first. It does that before the lock, while the users still work.

If the cut-over can't lock the files, it fails and shows the jobs which hold locks. Run it again when they are free.

If rows can't be applied (`RRN 4711: 23505 ...`), the cut-over fails before the swap and releases the locks. The rows are stored in `IRERRnnn` of the shadow library. Typical causes:
* old data which violates a new unique key;
* a column expression which fails for a row.

Correct the data and run the cut-over again.

If the configuration of a table (`columns`, `dependents`, `library_list`) changes after `db-prepare`, `db-copy` and `db-cutover` stop with an error.
Run `db-prepare` and `db-copy` again: the table is prepared and copied again from scratch.

The progress is in the log of the stage. The current state of each table:

```sql
SELECT TABLE_NO, PROD_LIB, PROD_FILE, PHASE, ROWS_COPIED, ROWS_APPLIED, COPY_NEXT_RRN, COPY_END_RRN, MESSAGE, UPDATE_TIME
  FROM S000000123.IRSTATE
```

Phases: `NEW` → `PREPARED` → `COPYING` → `COPIED` → `CUTOVER` → `SWAPPED` → `DONE` (or `FAILED`).

### Going back

After the cut-over the old table is in the backup library of the deployment (`B000000123`).
Changes made after the cut-over are only in the new table.


## Test procedure

Before the first real deployment, test it on a test system with a copy of the table (or a generated one):

1. Run `docs/db-deployment-spike.py`.
2. Create a deployment with the changed table, configure it in the custom data and run `db-prepare` and `db-copy`.
3. While `db-copy` runs, change the table with a test program or SQL, for example:

   ```sql
   -- new rows (reusing deleted records), changes, deletes, a key which moves to another row
   INSERT INTO PRODLIB.ORDERS (ID, ...) VALUES (...);
   UPDATE PRODLIB.ORDERS SET STS = 'C' WHERE ID BETWEEN 1000 AND 2000;
   DELETE FROM PRODLIB.ORDERS WHERE ID BETWEEN 5000 AND 5100;
   UPDATE PRODLIB.ORDERS SET ID = -1 WHERE ID = 10;
   UPDATE PRODLIB.ORDERS SET ID = 10 WHERE ID = 11;
   UPDATE PRODLIB.ORDERS SET ID = 11 WHERE ID = -1;
   ```

   Also with commitment control: change rows and roll the changes back.
4. Run `db-cutover`. Compare the old table (backup library) with the new one, using the column expressions. Both queries must return no rows:

   ```sql
   SELECT ID, NAME, DATE(TIMESTAMP_FORMAT(DIGITS(ORDDT8), 'YYYYMMDD')) FROM B000000123.ORDERS
   EXCEPT
   SELECT ID, NAME, ORDDAT FROM PRODLIB.ORDERS;

   SELECT ID, NAME, ORDDAT FROM PRODLIB.ORDERS
   EXCEPT
   SELECT ID, NAME, DATE(TIMESTAMP_FORMAT(DIGITS(ORDDT8), 'YYYYMMDD')) FROM B000000123.ORDERS;
   ```

5. Check the logical files and indexes (`DSPDBR PRODLIB/ORDERS`), the views, the authorities (`DSPOBJAUT`), the owner and the journaling (`DSPFD`) of the new table.


## Work tables in the shadow library

| Object | Content |
|---|---|
| `IRSTATE` | One row per table: phase, journal position, progress |
| `IROBJECTS` | Files which are replaced at the cut-over: the table and its dependent files |
| `IRMAPnnn` | RRN of each row in the old table (`SRC_RRN`) and in the new table (`TGT_RRN`) |
| `IRCHGnnn` | Rows of the old table which have changed and wait to be applied |
| `IRERRnnn` | Rows which can't be applied, with their error |
| `IRJRN`, `IRRCV*` | Journal and receivers, if the table hasn't been journaled before |

`nnn` is the position of the table in the configuration. The library is created with `CRTLIB` (not `CREATE SCHEMA`), so its tables are not journaled.
The generated SQL (new files, views) is in `db_deployment/` of the meta directory of the deployment.
