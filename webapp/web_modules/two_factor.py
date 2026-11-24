"""
Two-factor authentication with TOTP (docs/features/two-factor-authentication.md): the checks of the web app.

* Login: the code is checked before the password goes to the IBM i (`check_login_code`), and used after the login (`use_login_code`).
* Policy `C_2FA_POLICY`: off | optional | admins | required. A user who needs it and hasn't set it up can only set it up.
* Step-up: some actions need a code which has been entered in the last C_2FA_STEP_UP_MINUTES (`require_recent_code`).
"""
import logging
import time

from fastapi import Request

from etc import constants
from modules import current_user, errors, permission_config, permissions, totp
from modules.db import login_failure_data, user_mfa_data


POLICIES = ['off', 'optional', 'admins', 'required']

SESSION_CODE_TIME = 'mfa_at'
SESSION_SETUP_REQUIRED = 'mfa_setup_required'

# Paths a user can use who has to set up the two-factor authentication first
SETUP_PATHS = ['/user', '/logout', '/healthz', '/api/mfa/setup', '/api/mfa/enable']



class Step_Up_Required_Error(errors.App_Error):
    """The action needs a recent code of the authenticator app. The page asks for it and sends the request again."""
    status_code = 403



def get_policy() -> str:

    policy = getattr(constants, 'C_2FA_POLICY', 'optional')

    if policy not in POLICIES:
        logging.error(f"C_2FA_POLICY '{policy}' is invalid ({', '.join(POLICIES)}): 'required' is used")
        return 'required'

    return policy



def is_required(user: str) -> bool:
    """The user must have the two-factor authentication"""

    policy = get_policy()

    if policy == 'required':
        return True

    if policy == 'admins':
        return permission_config.is_user_allowed(user, permissions.PermissionAction.ADMIN)

    return False



def get_user_state(user: str) -> dict|None:
    """The setup of the user, None if the policy is `off` or the user has none (or hasn't confirmed it)"""

    if get_policy() == 'off':
        return None

    mfa = user_mfa_data.get(user)
    return mfa if mfa is not None and mfa['enabled'] else None



def _match_code(user: str, mfa: dict, code: str|None) -> tuple[str, object]|None:
    """
    Returns:
        ('step', step) for a valid code of the app, ('recovery', hash) for a recovery code which hasn't been used, None otherwise
    """

    if code is None or code.strip() == '':
        return None

    if totp.is_code_format(code):
        step = totp.verify(mfa['secret'], code, last_step=mfa['last_step'])
        return ('step', step) if step is not None else None

    # Checked without using it up: that happens after the login (use_login_code)
    code_hash = totp.hash_recovery_code(code)
    return ('recovery', code_hash) if user_mfa_data.has_recovery_code(user, code_hash) else None



def check_login_code(user: str, code: str|None) -> tuple[bool, tuple|None]:
    """
    Checks the code of the login, before the password is checked by the IBM i. Nothing is used up yet: a wrong password
    must not cost a recovery code.

    Returns:
        (ok, match): ok False if the user has the two-factor authentication and the code isn't valid (or too many wrong codes).
        match: what `use_login_code` needs after the login, None if the user has no two-factor authentication.
    """

    mfa = get_user_state(user)

    if mfa is None:
        return True, None

    if login_failure_data.is_code_blocked(user):
        logging.warning(f"Too many wrong codes of the two-factor authentication: {user=}")
        return False, None

    match = _match_code(user, mfa, code)

    if match is None:
        login_failure_data.add_code_failure(user)
        return False, None

    return True, match



def use_login_code(user: str, match: tuple) -> bool:
    """After the password: the code is used, so it can't be used again. False if it has been used meanwhile (or the recovery code isn't valid)."""

    kind, value = match

    if kind == 'step':
        used = user_mfa_data.use_step(user, value)
    else:
        used = user_mfa_data.use_recovery_code(user, value)
        if used:
            logging.warning(f"User {user} logged in with a recovery code")

    if not used:
        login_failure_data.add_code_failure(user)

    return used



def verify_code(user: str, code: str|None) -> bool:
    """A code of the app or a recovery code, used up if valid (step-up, turning off)"""

    mfa = get_user_state(user)

    if mfa is None or login_failure_data.is_code_blocked(user):
        return False

    match = _match_code(user, mfa, code)

    if match is None:
        login_failure_data.add_code_failure(user)
        return False

    # Counts a failure itself
    if not use_login_code(user, match):
        return False

    login_failure_data.clear_code_failures(user)
    return True



def after_login(session, user: str, match: tuple|None) -> None:

    if match is not None:
        session[SESSION_CODE_TIME] = time.time()
        login_failure_data.clear_code_failures(user)

    elif is_required(user):
        # Can only set it up (docs/features/two-factor-authentication.md, requirement 13)
        session[SESSION_SETUP_REQUIRED] = True



def check_setup_required(session, user: str|None) -> bool:
    """
    The session has to set up the two-factor authentication first. The flag of the login is checked again: since the login,
    the policy may have been loosened (restart), the user may have lost the permission `admin`, or set it up in another session.
    Then the flag is removed (docs/bugfixes/2fa-setup-flag-outlives-policy.md).
    """

    if not session.get(SESSION_SETUP_REQUIRED):
        return False

    if user is not None and is_required(user) and get_user_state(user) is None:
        return True

    session.pop(SESSION_SETUP_REQUIRED, None)
    return False



def require_session(request: Request) -> None:
    """Actions of the account: only in the web app, not with an API token"""

    if getattr(request.state, 'session', None) is None or request.state.session.transient:
        raise errors.Permission_Denied_Error("Only possible in the web app, not with an API token")



def require_recent_code(request: Request) -> None:
    """
    Step-up: a code of the app in the last C_2FA_STEP_UP_MINUTES. Users without two-factor authentication
    can't give one (with the policy `optional`); for them it isn't required.

    Raises:
        Step_Up_Required_Error
    """

    require_session(request)
    user = current_user.get_user()

    if get_user_state(user) is None:
        return

    entered = request.state.session.get(SESSION_CODE_TIME) or 0

    if time.time() - entered > constants.C_2FA_STEP_UP_MINUTES * 60:
        raise Step_Up_Required_Error("Enter the code of your authenticator app to confirm this action")
