import datetime
from enum import Enum
import os, pathlib, json, logging
import hashlib, mmap
import time
from dataclasses import is_dataclass, asdict


file_cache = {}


class DataclassJSONEncoder(json.JSONEncoder):
  def default(self, o):
    if is_dataclass(o):
      return asdict(o)
    if isinstance(o, Enum):
      return o.value
    return super().default(o)




def get_file_hash(filename):
    
  if os.path.getsize(filename) == 0:
    return ''

  h  = hashlib.md5()
  with open(filename, "rb") as f:
    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
      h.update(mm)
  return h.hexdigest()




def readFile(file, use_cache=False):
  if use_cache and file in file_cache:
    return get_cached_file(file)

  with open(file, 'r', encoding='utf-8') as text_file:
    content = text_file.read()
    if use_cache:
      add_file_to_cache(file, content)
    return content



def writeText(content, file, write_empty_file=False, encoding='utf-8', mode='w'):
  
  
  if file is None or len(content) == 0 and not write_empty_file:
    return

  logging.debug(f"Write Textfile: {os.path.abspath(file)=}; {len(content)} Bytes")

  # Create dir if not exist
  pathlib.Path(os.path.dirname(file)).mkdir(parents=True, exist_ok=True)

  with open(file, mode, encoding=encoding) as text_file:
    text_file.write(content)



def get_cached_file(file):

  return file_cache[file]['data']


def add_file_to_cache(file, data):
  file_cache[file] = {
    'data': data,
    'timestamp': datetime.datetime.now(),
    'hash': get_file_hash(file)
  }



def getJson(file, retry=False, use_cache=False):

  if use_cache and file in file_cache:
    return get_cached_file(file)

  for attempt in range(5):
    try:
      with open(file, 'r') as f:
        text = f.read()
        d = json.loads(text)
        if use_cache:
          add_file_to_cache(file, d)
        return d
    except Exception as e:
      if attempt > 4 or not retry:
        logging.error(f"Failed to read JSON file {file} after {attempt+1} attempts")
        logging.exception(e, stack_info=True)
        raise e
      time.sleep(0.1)
  
  return None


def writeJson(content, file):
  
  if file is None:
    return

  #logging.debug(content)
  # Create dir if not exist
  pathlib.Path(os.path.dirname(file)).mkdir(parents=True, exist_ok=True)

  with open(file, 'w') as json_file:
    json.dump(content, json_file, indent=2, ensure_ascii=False, cls=DataclassJSONEncoder)

