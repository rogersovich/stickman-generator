import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from client import Client, NotOurs, Offline

JOB = {"project_id": "p", "scene_index": 0, "text": "Halo."}


class Handler(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *args):
        pass

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        Handler.seen.append((self.command, self.path, dict(self.headers), body))
        return body

    def do_POST(self):
        self._record()
        if self.path.endswith("/claim"):
            payload = json.loads(Handler.seen[-1][3])
            if payload["models"] == ["omnivoice"]:
                self._send(200, json.dumps(JOB).encode())
            else:
                self._send(204)
        else:
            self._send(204)

    def do_PUT(self):
        self._record()
        self._send(409 if "/9/" in self.path else 204)

    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    Handler.seen = []
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_claim_returns_job_or_none(server):
    c = Client(server, "tok", "mac")
    assert c.claim(["omnivoice"], "MPS") == JOB
    assert c.claim(["voxcpm2"], "MPS") is None


def test_put_result_sends_auth_name_and_wav(server):
    Client(server, "tok", "pc").put_result("p", 0, "k1", b"RIFF....WAVEdata")
    method, path, headers, body = Handler.seen[-1]
    assert (method, path) == ("PUT", "/api/tts-worker/jobs/p/0/result?key=k1")
    assert headers["Authorization"] == "Bearer tok" and headers["X-Worker-Name"] == "pc"
    assert body.startswith(b"RIFF")


def test_no_token_sends_no_auth_header(server):
    Client(server, "", "mac").heartbeat(["omnivoice"], "MPS")
    assert "Authorization" not in Handler.seen[-1][2]


def test_conflict_raises_not_ours(server):
    with pytest.raises(NotOurs):
        Client(server, "tok", "pc").put_result("p", 9, "k", b"RIFF")


def test_closed_port_raises_offline():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(Offline):
        Client(f"http://127.0.0.1:{port}", "", "mac").claim(["omnivoice"], "MPS")
