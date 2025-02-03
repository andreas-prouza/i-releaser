import logging, time
import socketio


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


  async def watch_project_summary(self, sid, req_data):
      logging.info(f"Watch: start {sid=}, {req_data=}")
      
      await self.sio.emit("projects", {'project': 3}, to=sid)
      #logging.info(f"Notify: end")
      time.sleep(5)



