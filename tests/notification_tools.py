"""
Servers for the tests of the notifications (docs/features/notifications.md): a mail server and a webhook.
Both run in a thread of the test and keep what they receive. `smtpd` has been removed from Python.
"""
import email, email.policy, http.server, json, socketserver, threading, time



def wait_for(get_items, count: int, timeout: float=15) -> list:
    """The received items, once there are `count` (more are a failure of the test, checked by the caller)"""

    end = time.time() + timeout
    while time.time() < end:
        items = get_items()
        if len(items) >= count:
            return items
        time.sleep(0.05)

    raise AssertionError(f"Expected {count} items, got {len(get_items())} after {timeout} seconds")



def _address(text: str) -> str:
    """`<a@b.c> BODY=8BITMIME` -> a@b.c"""

    text = text.strip()
    if text.startswith('<'):
        return text[1:text.index('>')]
    return text.split()[0]



class SMTP_Server:
    """Accepts every mail. `reject` (number) refuses the next mails with a temporary error (451)."""

    def __init__(self):

        self.messages: list[dict] = []
        self.reject = 0
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                outer._handle(self)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


    def _handle(self, handler) -> None:

        def reply(text: str) -> None:
            handler.wfile.write(f"{text}\r\n".encode())
            handler.wfile.flush()

        reply('220 test ESMTP')
        sender, recipients = None, []

        while True:
            line = handler.rfile.readline()
            if not line:
                return

            command = line.decode('utf-8', 'replace').strip()
            upper = command.upper()

            if upper.startswith('EHLO'):
                reply('250-test')
                reply('250 8BITMIME')
            elif upper.startswith('HELO'):
                reply('250 test')
            elif upper.startswith('MAIL FROM:'):
                if self.reject > 0:
                    self.reject -= 1
                    reply('451 Try again later')
                    continue
                sender, recipients = _address(command[10:]), []
                reply('250 OK')
            elif upper.startswith('RCPT TO:'):
                recipients.append(_address(command[8:]))
                reply('250 OK')
            elif upper == 'DATA':
                reply('354 End data with <CR><LF>.<CR><LF>')
                lines = []
                while True:
                    data = handler.rfile.readline()
                    if data in (b'.\r\n', b'.\n', b''):
                        break
                    lines.append(data[1:] if data.startswith(b'..') else data)
                self.messages.append({'sender': sender, 'recipients': recipients,
                                      'message': email.message_from_bytes(b''.join(lines), policy=email.policy.default)})
                reply('250 OK')
            elif upper == 'QUIT':
                reply('221 Bye')
                return
            else:
                reply('250 OK')


    def channel(self, **values) -> dict:
        return {'type': 'email', 'host': '127.0.0.1', 'port': self.port, 'tls': 'none', 'sender': 'i-releaser@example.com', **values}


    def wait_for(self, count: int, timeout: float=15) -> list[dict]:
        return wait_for(lambda: self.messages, count, timeout)


    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()



class Webhook_Server:
    """Keeps the JSON of each POST and answers with `status`"""

    SECRET_PATH = '/workflows/secret-token-123/invoke'

    def __init__(self, status: int=202):

        self.requests: list[dict] = []
        self.status = status
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                outer.requests.append({'path': self.path, 'content_type': self.headers.get('Content-Type'), 'body': json.loads(body)})
                self.send_response(outer.status)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}{self.SECRET_PATH}"


    def channel(self, format: str='json') -> dict:
        return {'type': 'webhook', 'format': format, 'url': self.url}


    def wait_for(self, count: int, timeout: float=15) -> list[dict]:
        return wait_for(lambda: self.requests, count, timeout)


    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
