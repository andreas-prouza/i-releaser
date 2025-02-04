import os, logging
from pathlib import Path
from etc import constants

from watchdog.events import FileSystemEventHandler


def create_dir_if_not_exist(path: str=None) -> None:

  path_2_check=Path(path)
  if not Path.exists(path_2_check):
      os.makedirs(path_2_check)



def create_dir_of_file_if_not_exist(file: str=None) -> None:

  path_2_check = os.path.dirname(file)
  create_dir_if_not_exist(path_2_check)





class DirHandler(FileSystemEventHandler):


  def __init__(self, observer):
    self.observer = observer

  def on_any_event(self, event):

    logging.debug(f"Event: {event=}")
    
    if event.is_directory:
      return None

    if os.path.basename(event.src_path)[0:15] != constants.C_DEPLOY_FILE_PREFIX:
      return None

    if event.event_type in ['modified']:
      self.observer.stop()
      