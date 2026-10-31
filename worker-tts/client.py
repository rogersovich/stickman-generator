"""HTTP client for the backend's /api/tts-worker endpoints (stdlib only)."""

import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 30


class Offline(Exception):
    """The backend can't be reached."""


class NotOurs(Exception):
    """The backend gave this scene to someone else (our lease expired)."""


class Client:
    def __init__(self, server: str, token: str, name: str):
        self.base = server.rstrip("/") + "/api/tts-worker"
        self.token = token
        self.name = name

    def _request(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None, extra_headers: dict | None = None):
        req = urllib.request.Request(self.base + path, data=body, method=method)
        req.add_header("X-Worker-Name", self.name)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        if content_type:
            req.add_header("Content-Type", content_type)
        if extra_headers:
            for k, v in extra_headers.items():
                req.add_header(k, str(v))
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as e:
            if e.code == 409:
                raise NotOurs(e.read().decode(errors="ignore")) from e
            raise RuntimeError(f"backend {e.code}: {e.read().decode(errors='ignore')[:300]}") from e
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise Offline(str(e)) from e

    def _json(self, method: str, path: str, payload: dict):
        return self._request(method, path, json.dumps(payload).encode(), "application/json")

    def heartbeat(self, models: list[str], device: str) -> None:
        self._json("POST", "/heartbeat", {"name": self.name, "models": models, "device": device})

    def claim(self, models: list[str], device: str) -> dict | None:
        status, body = self._json("POST", "/claim", {"name": self.name, "models": models, "device": device})
        return json.loads(body) if status == 200 and body else None

    def voice_audio(self, voice_id: str) -> bytes:
        return self._request("GET", f"/voices/{voice_id}/audio")[1]

    def put_result(self, project_id: str, index: int, key: str, wav: bytes, audit: dict | None = None) -> None:
        query = urllib.parse.urlencode({"key": key})
        extra = {}
        if audit:
            import base64
            audit_json = json.dumps(audit)
            extra["X-Worker-Audit"] = base64.b64encode(audit_json.encode('utf-8')).decode('ascii')
        self._request("PUT", f"/jobs/{project_id}/{index}/result?{query}", wav, "audio/wav", extra_headers=extra)

    def put_group_result(self, project_id: str, first_index: int, key: str, wav: bytes) -> None:
        query = urllib.parse.urlencode({"key": key, "is_group": "true"})
        self._request("PUT", f"/jobs/{project_id}/{first_index}/result?{query}", wav, "audio/wav")

    def fail(self, project_id: str, index: int, error: str) -> None:
        self._json("POST", f"/jobs/{project_id}/{index}/fail", {"error": error[:500]})
