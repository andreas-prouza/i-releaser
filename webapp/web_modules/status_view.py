"""
How a status is shown in the web app: kind (its colour), icon and text. The one mapping for all pages,
used by the macro `status_pill` (templates/components/ui.html). See docs/features/web-ui-layout.md#components.

The values are those of the status classes (deployments, stages, steps, objects, jobs). They overlap,
so one table is enough. An unknown value is shown neutral with its own text.
"""
from dataclasses import dataclass
from enum import Enum


# The kinds have a colour each in app.css: --ir-<kind>, class k-<kind>
KINDS = ('neutral', 'ready', 'running', 'queued', 'success', 'danger', 'canceled')



@dataclass(frozen=True)
class Status_View:
    value: str
    kind: str
    icon: str       # name of a Bootstrap Icon without "bi-"
    text: str
    spin: bool = False



def _view(value: str, kind: str, icon: str, text: str|None=None, spin: bool=False) -> Status_View:
    return Status_View(value=value, kind=kind, icon=icon, text=text or value, spin=spin)



STATUS = {view.value: view for view in [
    _view('new', 'neutral', 'circle'),
    _view('ready', 'ready', 'play-circle'),
    _view('in process', 'running', 'arrow-repeat', spin=True),
    _view('running', 'running', 'arrow-repeat', spin=True),
    _view('in preperation', 'running', 'hourglass-split', 'in preparation'),
    _view('prepare', 'running', 'hourglass-split', 'preparing'),
    _view('queued', 'queued', 'clock'),
    _view('finished', 'success', 'check-lg'),
    _view('failed', 'danger', 'x-lg'),
    _view('canceled', 'canceled', 'slash-circle'),

    # Objects: the work on an object, and what is done with it
    _view('saving', 'running', 'arrow-repeat', spin=True),
    _view('in transfer', 'running', 'arrow-repeat', spin=True),
    _view('in backup', 'running', 'arrow-repeat', spin=True),
    _view('restoring', 'running', 'arrow-repeat', spin=True),
    _view('in build', 'running', 'arrow-repeat', spin=True),
    _view('saved', 'success', 'check-lg'),
    _view('transferred', 'success', 'check-lg'),
    _view('backuped', 'success', 'check-lg', 'backed up'),
    _view('restored', 'success', 'check-lg'),
    _view('builded', 'success', 'check-lg', 'built'),
]}

UNKNOWN_ICON = 'dot'
NONE_TEXT = '–'



def get_status_view(status) -> Status_View:
    """`status`: a value of a status class, its string, or None"""

    if isinstance(status, Enum):
        status = status.value

    if status is None or str(status).strip() == '':
        return Status_View(value='', kind='neutral', icon=UNKNOWN_ICON, text=NONE_TEXT)

    value = str(status)

    return STATUS.get(value.strip().lower(), Status_View(value=value, kind='neutral', icon=UNKNOWN_ICON, text=value))
