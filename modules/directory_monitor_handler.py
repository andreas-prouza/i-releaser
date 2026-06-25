import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DirectoryMonitorHandler(FileSystemEventHandler):
    """
    A custom event handler that listens for specific file system events.
    """
    
    def on_created(self, event):
        if event.is_directory:
            print(f"📁 Directory Created: {event.src_path}")
        else:
            print(f"📄 File Created: {event.src_path}")

    def on_modified(self, event):
        if event.is_directory:
            print(f"📁 Directory Modified: {event.src_path}")
        else:
            print(f"📄 File Modified: {event.src_path}")

    def on_deleted(self, event):
        if event.is_directory:
            print(f"❌ Directory Deleted: {event.src_path}")
        else:
            print(f"❌ File Deleted: {event.src_path}")


# # 2. Initialize the event handler and the observer
#    event_handler = DirectoryMonitorHandler()
#    observer = Observer()
#
#    # 3. Schedule the observer to watch the directory
#    # Set recursive=True to monitor all subdirectories as well
#    observer.schedule(event_handler, path_to_watch, recursive=True)
#
#    # 4. Start the observer thread
#    observer.start()