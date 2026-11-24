"""Writes events of the web app to the audit log (docs/features/audit-log.md)"""
from fastapi import Request

from modules import current_user, permissions
from modules.db import audit_data



def record(request: Request|None, event: str, object: str|None=None, details: dict|None=None, result: str='ok', user: str|None=None) -> None:
    """The user of the request (or `user`, e.g. a failed login) and the client address"""

    client = request.client.host if request is not None and request.client else None
    user = user if user is not None else current_user.get_user()
    # User profiles have no case: always in lower case
    audit_data.add(event, user=user.lower() if user else None, client=client, object=object, details=details, result=result)



def describe(entry) -> set[str]:
    """The permissions of a user or role as texts, to compare them: `general: run`, `workflow erp: run`, `stage erp/PROD: run`, `role: admins`"""

    def value(action) -> str:
        return action.value if isinstance(action, permissions.PermissionAction) else str(action)

    result = {f"general: {value(a)}" for a in entry.permissions.general or []}

    for workflow, wf_permissions in (entry.permissions.workflows or {}).items():
        wf_permissions = wf_permissions or {}
        result |= {f"workflow {workflow}: {value(a)}" for a in wf_permissions.get('general') or []}
        for stage, actions in (wf_permissions.get('stages') or {}).items():
            result |= {f"stage {workflow}/{stage}: {value(a)}" for a in actions or []}

    result |= {f"role: {role}" for role in getattr(entry, 'roles', None) or []}
    return result



def get_changes(before: dict, after: dict) -> dict:
    """{name: {'added': [...], 'removed': [...]}} of users or roles which have changed"""

    changes = {}

    for name in sorted(set(before) | set(after)):
        old = describe(before[name]) if name in before else set()
        new = describe(after[name]) if name in after else set()
        if old != new or (name in before) != (name in after):
            change = {'added': sorted(new - old), 'removed': sorted(old - new)}
            if name not in after:
                change['deleted'] = True
            if name not in before:
                change['new'] = True
            changes[name] = change

    return changes
