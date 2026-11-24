# The login can be used to disable IBM i profiles

- **Status:** finished (2026-11-23; tested with `tests/test_login.py`, not on IBM i)
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

The login checks the password with an ODBC connect to the IBM i ([app_login.py:75](../../webapp/web_modules/app_login.py#L75)).
Every wrong password is an invalid sign-on attempt on the IBM i. The system values `QMAXSIGN` and `QMAXSGNACN` decide what happens after too many of them.
The IBM default for both is 3, so the third consecutive failure disables the user profile.

The lockout of i-Releaser ([login_failure_data.py](../../modules/db/login_failure_data.py)) doesn't prevent that:

* `C_LOGIN_MAX_FAILURES = 5` ([constants.py:47](../../etc/constants.py#L47)) is higher than the default of `QMAXSIGN`.
  [installation.md](../installation.md) tells you to keep it below `QMAXSIGN`, but the shipped default isn't.
* The counter only covers a time window (`C_LOGIN_BLOCK_MINUTES = 15`).
  The IBM i counts *consecutive* failures until the next successful sign-on, so after 15 minutes the next attempts add to the same counter on the IBM i.
* Anyone who can reach the login page can do this for any user listed in `etc/user_permissions.json`. Users which aren't listed never reach the ODBC connect (good).

So with the defaults, three requests by an anonymous attacker disable the IBM i profile of an i-Releaser user (and of an admin).


## Requirements

1. i-Releaser never causes more than `C_LOGIN_MAX_FAILURES` consecutive failed sign-ons of a profile on the IBM i:
   the counter per user counts consecutive failures without a time window. Only a successful login clears it.
2. `C_LOGIN_MAX_FAILURES` defaults to 2 (below the IBM default 3). The web app warns at start if it's 3 or higher.
3. A user blocked by requirement 1 is unblocked by an admin in the web app (settings page, `Blocked logins`, button `Unblock`). Not by time, see [decisions](#decisions-2026-11-23).
4. The block per client address (IP) keeps its time window.
5. The message for the user stays the same for "wrong password" and "blocked" (no user enumeration).
6. Each block and unblock is recorded in the [audit log](../features/audit-log.md) (as soon as it exists; until then in the application log at `WARNING`).
7. Documentation: `installation.md` explains the relation to `QMAXSIGN`/`QMAXSGNACN` and the [2FA](../features/two-factor-authentication.md), which checks the code before the IBM i sign-on.


## Acceptance criteria

- [x] Test: with `C_LOGIN_MAX_FAILURES = 2`, a third wrong password for the same user doesn't reach the ODBC connect, also after the block time has passed.
- [x] ~~Test: after the block time, exactly one more attempt reaches the connect.~~ Dropped, see decisions.
- [x] Test: a successful login clears the counter.
- [x] Test: an admin can unblock a user, a non-admin can't.
- [x] Test: the start warns with `C_LOGIN_MAX_FAILURES = 3`.
- [x] Test: logins which don't reach the IBM i (invalid input, no answer) don't count for the user.


## Non-goals

* Reading `QMAXSIGN` from the IBM i (it would need a connection without a user).


## Decisions (2026-11-23)

* **No unblock by time.** One more attempt after the block time would be the third failure in a row on the IBM i (with `QMAXSIGN` 3), which is what the block prevents. Only an admin unblocks, or a successful login before the limit is reached.
* **Separate limit for client addresses** (`C_LOGIN_CLIENT_MAX_FAILURES`, default 10): with the limit of 2, users behind one proxy address would block each other.
* Only failed sign-ons count for the user; invalid input and a sign-on without answer (timeout) count for the client only.
* If all admins are blocked, the row is deleted in the database (`installation.md`).

## Open questions

* None.
