import logging, time
import socketio

from watchdog.observers import Observer

from etc import constants
from modules import workflow, deploy_version, file_utils, deploy_version


class SocketHandlers:


  def __init__(self, sio: socketio.AsyncServer):
    self.sio = sio


  async def connect(self, sid, environ, parm2=None):
      """event listener when client connects to the server"""
      logging.info(f"client has connected {sid=}")



  async def disconnect(self, sid):
      logging.info(f'disconnect {sid=}')
      #await drop_session(sid)


  async def notify(self, sid, req_data):
      logging.info(f"Notify: start {sid=}, {req_data=}")
      await self.sio.emit("projects", {'project': 3}, to=sid)
      #logging.info(f"Notify: end")
      time.sleep(5)


  async def watch_project_summary(self, sid, project_filter:[str]=None):
      logging.info(f"Watch: start {sid=}, {project_filter=}")
      
      file_utils.create_dir_if_not_exist(constants.C_DEPLOY_FILE_DIR)

      # Wait until something has changed
      observer = Observer()
      event_handler = file_utils.DirHandler(observer)
      observer.schedule(event_handler, constants.C_DEPLOY_FILE_DIR, recursive=False)
      observer.start()
      observer.join()

      logging.info("Change detected")

      projects = workflow.Workflow.get_all_projects()
      
      summary={}

      for project in projects:
        file = constants.C_DEPLOY_VERSION.format(project=project)
        deployments: deploy_version.Deployments = deploy_version.Deploy_Version.get_deployments(file)

        if deployments is None:
          continue

        ready_counter = 0
        for dp in deployments['deployments']:
          if dp['status'] == 'ready':
            ready_counter += 1

        summary[project] = {'ready' : ready_counter}

      logging.info(f"Send back to client: {summary}")
      await self.sio.emit("projects", summary, to=sid)



