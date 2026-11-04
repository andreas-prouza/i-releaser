# Login: user and password are put into the ODBC connection string unquoted

- **Status:** ready (Implemented. Open: the check on IBM i.)
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review (not verified on IBM i)
- **Confidential:** don't publish before the fix is released


## Current situation

The login builds the connection string with an f-string ([app_login.py:20](../../webapp/web_modules/app_login.py#L20)):

```python
connection_string = f"driver={driver};system={host};uid={user};pwd={password}"
```

* A `;` in the password adds further keywords, e.g. `x;SYSTEM=other.host;UID=me;PWD=mine`.
  Whether this can log in against another system depends on how the IBM i Access ODBC Driver handles repeated keywords (first or last one wins).
  If the last one wins, a user can log in with an account of another system under any listed user name.
* Passwords containing `;`, `{` or `}` can't log in.
* The user name isn't checked before the connection.
* There is no limit for failed logins. Each failed login counts for the IBM i profile (`QMAXSIGN`), so anyone who can reach the login page can disable IBM i profiles.


## Requirements

1. User and password are quoted according to the ODBC rules (value in `{...}`, `}` doubled), e.g. with `quote_odbc_value` of `modules/db_deployment/connection.py`.
2. The user name has to be a valid IBM i profile name (`^[A-Za-z$#@][A-Za-z0-9$#@_]{0,9}$`) and listed in `etc/user_permissions.json` **before** the ODBC connection is tried. Otherwise no connection is made.
3. Control characters in user or password are rejected.
4. Failed logins are limited per user and per client address (e.g. delay or lock for some minutes after N failures), before the IBM i profile is disabled.
5. The error message doesn't tell whether the user or the password was wrong.


## Acceptance criteria

- [x] Unit test (ODBC connect mocked): password `x;SYSTEM=other;UID=a;PWD=b` → exactly one connection string with the quoted password, `SYSTEM` from `db_config.py`.
- [x] Unit test: user names with invalid characters or not in the permission file → no connection attempt.
- [x] Unit test: after N failed logins further attempts are rejected without a connection attempt for the configured time.
- [ ] Checked on IBM i: a password with `;`, `{`, `}` works.


## Non-goals

* Other login methods (Kerberos, SSO)


## Decisions

* Does the driver accept `{...}` for `PWD`? **Can't be checked here. Only values with special characters get quoted, so normal passwords don't change. You check it once on IBM i.**
* Limit for failed logins? **5 failures per user and client address, then 15 minutes blocked.**
