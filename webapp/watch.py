# import time module, Observer, FileSystemEventHandler
import os, time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class OnMyWatch:
  # Set the directory on watch
  watchDirectory = "../etc"

  def __init__(self):
    self.observer = Observer()

  def run(self):
    event_handler = Handler(self.observer)
    self.observer.schedule(event_handler, self.watchDirectory, recursive = True)
    self.observer.start()

    self.observer.join()


class Handler(FileSystemEventHandler):


  def __init__(self, observer):
    self.observer = observer

  def on_any_event(self, event):

    print(os.path.basename(event.src_path))
    print(f"Event: {event.event_type}")

    if event.event_type == 'created':
      # Event is created, you can process it now
      print("Watchdog received created event - % s." % event.src_path)
    elif event.event_type == 'modified':
      # Event is modified, you can process it now
      print("Watchdog received modified event - % s." % event.src_path)

    #self.observer.stop()
      

if __name__ == '__main__':
  watch = OnMyWatch()
  watch.run()
