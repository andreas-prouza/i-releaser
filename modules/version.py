import os


with open(os.path.join(os.path.dirname(__file__), '..', 'VERSION'), encoding='utf-8') as version_file:
  APP_VERSION: str = version_file.read().strip()
