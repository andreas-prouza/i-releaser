import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

class DirectoryMonitorHandler(FileSystemEventHandler):
    """
    A custom event handler that listens for specific file system events.
    """
    
    def on_created(self, event):
        if event.is_directory:
            logging.info(f"📁 Directory Created: {event.src_path}")
        else:
            logging.info(f"📄 File Created: {event.src_path}")

    def on_modified(self, event):
        if event.is_directory:
            logging.info(f"📁 Directory Modified: {event.src_path}")
        else:
            logging.info(f"📄 File Modified: {event.src_path}")

    def on_deleted(self, event):
        if event.is_directory:
            logging.info(f"❌ Directory Deleted: {event.src_path}")
        else:
            logging.info(f"❌ File Deleted: {event.src_path}")

def start_monitoring(path):
    event_handler = DirectoryMonitorHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    logging.info(f"Started monitoring directory: {path}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def start_monitoring_in_thread(path):
    monitor_thread = threading.Thread(target=start_monitoring, args=(path,))
    monitor_thread.daemon = True
    monitor_thread.start()
