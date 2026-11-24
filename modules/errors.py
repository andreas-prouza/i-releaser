"""
Errors which are meant for the caller, with their HTTP status.
All other exceptions are unexpected: the caller only gets a general message and the details go to the log.
"""


class App_Error(Exception):
    status_code = 500


class Invalid_Input_Error(App_Error):
    status_code = 422


class Not_Logged_In_Error(App_Error):
    status_code = 401


class Permission_Denied_Error(App_Error):
    status_code = 403


class Not_Found_Error(App_Error):
    status_code = 404


class Conflict_Error(App_Error):
    """Not possible in the current status, e.g. the stage is already running"""
    status_code = 409


class Bad_Gateway_Error(App_Error):
    """Another server has refused or not answered, e.g. the mail server of a notification"""
    status_code = 502


class Service_Unavailable_Error(App_Error):
    """Can't be done now, e.g. too many logins at the same time. Try again later."""
    status_code = 503
