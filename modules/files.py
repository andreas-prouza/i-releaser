import os, pathlib, json, logging
import hashlib, mmap
import time



def get_file_hash(filename):
    
  if os.path.getsize(filename) == 0:
    return ''

  h  = hashlib.md5()
  with open(filename, "rb") as f:
    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
      h.update(mm)
  return h.hexdigest()



def readText(file):
  with open(f"{os.path.dirname(__file__)}/../{file}", 'r') as text_file:
    return str(text_file.read())


def readFile(file):
  with open(file, 'r', encoding='utf-8') as text_file:
    return text_file.read()



def writeText(content, file, write_empty_file=False, encoding='utf-8', mode='w'):
  
  
  if file is None or len(content) == 0 and not write_empty_file:
    return

  logging.debug(f"Write Textfile: {os.path.abspath(file)=}; {len(content)} Bytes")

  # Create dir if not exist
  pathlib.Path(os.path.dirname(file)).mkdir(parents=True, exist_ok=True)

  with open(file, mode, encoding=encoding) as text_file:
    text_file.write(content)



def getJson(file, retry=False):

  for attempt in range(5):
    try:
      with open(file, 'r') as f:
        return json.load(f)
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
    json.dump(content, json_file, indent=2, ensure_ascii=False)

