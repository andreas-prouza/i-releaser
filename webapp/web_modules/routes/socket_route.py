import logging, time
import socketio

from etc import constants
from modules import workflow, deploy_version


class SocketHandlers:


  def __init__(self, sio: socketio.AsyncServer):
    self.sio = sio


  async def connect(self, sid, environ, parm2=None):
      """event listener when client connects to the server"""
      logging.info(f"client has connected {sid=} {environ=}")



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
      
      observer = Observer()
      event_handler = Handler(observer)
      observer.schedule(event_handler, constants.C_DEPLOY_FILE_DIR, recursive=False)
      observer.start()
      observer.join()

      projects = workflow.Workflow.get_all_projects()
      for project in projects:
        file = constants.C_DEPLOY_VERSION.format(project=project)
        deploy_version.Deploy_Version.get_deployments(file)

      await self.sio.emit("projects", {'project': 3}, to=sid)
      #logging.info(f"Notify: end")
      time.sleep(5)



