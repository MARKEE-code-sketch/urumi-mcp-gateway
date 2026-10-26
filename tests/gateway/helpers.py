import asyncio
from contextlib import contextmanager
import secrets
import socket
from threading import Thread
import time

import uvicorn

from scripts.m6.harness import build
from scripts.m6.fixtures import fixture_app


class LocalServer:
    def __init__(self, app, **options):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        self.url = f"{'https' if options else 'http'}://127.0.0.1:{sock.getsockname()[1]}"
        self.server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='critical', **options))
        self.thread = Thread(target=self.server.run, kwargs={'sockets': [sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        if not self.server.started:
            raise RuntimeError('Fixture server did not start.')

    def close(self):
        self.server.should_exit = True
        self.thread.join(3)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(2)
        if self.thread.is_alive():
            raise RuntimeError('Fixture server did not close.')


def tokens():
    return {key: secrets.token_urlsafe(32) for key in
            ('key-a', 'key-b', 'session-a', 'session-b', 'bearer-token', 'header-token')}


@contextmanager
def environment(stateful=False):
    values = tokens()
    peers = {mode: LocalServer(fixture_app(mode, values.get(mode + '-token', ''), stateful))
             for mode in ('none', 'bearer', 'header')}
    app = build({mode: peer.url + '/mcp' for mode, peer in peers.items()}, values)
    gateway = LocalServer(app)
    try:
        yield app.app.state.router, gateway, peers, values
    finally:
        gateway.close()
        for peer in peers.values():
            peer.close()
