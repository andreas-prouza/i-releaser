import os
from pathlib import Path


def create_dir_if_not_exist(path: str=None) -> None:

  path_2_check=Path(path)
  if not Path.exists(path_2_check):
      os.makedirs(path_2_check)



def create_dir_of_file_if_not_exist(file: str=None) -> None:

  path_2_check = os.path.dirname(file)
  create_dir_if_not_exist(path_2_check)