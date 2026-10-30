"""Test harness: a fake Gemini server and a fake llama-server (Qwen) on localhost, so the real HTTP
client code in noah/llm.py is exercised end to end. Nothing here talks to Google."""

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _State:
    gemini_mode = "ok"        # ok | 500 | 404 | 400 | empty | 404-first
    gemini_calls = []
    llama_mode = "ok"         # ok | 500
    llama_calls = []

    @classmethod
    def reset(cls):
        cls.gemini_mode, cls.llama_mode = "ok", "ok"
        cls.gemini_calls, cls.llama_calls = [], []


def gemini_text_for(body):
    """What the fake Gemini says, decided from the request it received."""
    system = ((body.get("systemInstruction") or {}).get("parts") or [{}])[0].get("text", "")
    user = body["contents"][-1]["parts"][0]["text"]
    json_mode = (body.get("generationConfig") or {}).get("responseMimeType") == "application/json"
    if "Translate each string" in system:
        strings = json.loads(user)
        return json.dumps({"t": [f"[xx] {s}" for s in strings]}, ensure_ascii=False)
    if json_mode and "<topic" in user:
        if "NOTSTUDY" in user:
            return json.dumps({"error": "not_a_study_topic"})
        if "flashcards" in user:
            return json.dumps({"cards": [{"front": f"Term {i}", "back": f"Meaning {i}"} for i in range(8)]})
        qs = [{"q": f"Question {i}?", "options": ["A", "B", "C", "D"], "answer": i % 4, "explain": "Because."} for i in range(5)]
        qs.append({"q": "broken", "options": ["A", "A"], "answer": 9})
        return json.dumps({"questions": qs})
    if "UNKNOWNQ" in user:
        return "[[UNKNOWN]] I do not have that detail. The admissions office can help."
    if "WRONGFEE" in user:
        return "The fee is ₹12,345 per year."
    if "OPENADVISOR" in user:
        return "Let me help you choose. [[OPEN:advisor]]"
    if "MODELCRISIS" in user:
        return "[[CRISIS]]"
    if "<topic" in user or "study helper" in system:
        return "Tutor says: " + user[:40]
    return "Gemini says: " + user[:60]


class _GeminiHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        model = self.path.split("/models/")[1].split(":")[0]
        _State.gemini_calls.append({"model": model, "path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
        mode = _State.gemini_mode
        if mode == "404" or (mode == "404-first" and model == "gemini-3.5-flash-lite"):
            return self._json(404, {"error": {"message": "model not found"}})
        if mode == "500":
            return self._json(500, {"error": {"message": "boom"}})
        if mode == "400":
            return self._json(400, {"error": {"message": "API key not valid"}})
        text = "" if mode == "empty" else gemini_text_for(body)
        if "streamGenerateContent" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(0, len(text), 7):
                chunk = {"candidates": [{"content": {"parts": [{"text": text[i:i + 7]}]}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\r\n\r\n".encode())
                self.wfile.flush()
            return
        self._json(200, {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class _LlamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        _State.llama_calls.append(body)
        if _State.llama_mode == "500":
            self.send_response(500)
            self.end_headers()
            return
        user = body["messages"][-1]["content"]
        text = "Qwen says: " + user[:50]
        if body.get("response_format"):
            text = gemini_text_for({"contents": [{"parts": [{"text": user}]}], "generationConfig": {"responseMimeType": "application/json"},
                                    "systemInstruction": {"parts": [{"text": body["messages"][0]["content"]}]}})
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for i in range(0, len(text), 9):
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': text[i:i + 9]}}]})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        raw = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


_gemini_srv = _serve(_GeminiHandler)
_llama_srv = _serve(_LlamaHandler)

_tmp = tempfile.mkdtemp(prefix="noah-test-")
os.environ.update({
    "NOAH_DB_PATH": os.path.join(_tmp, "boot.db"),
    "NOAH_SECRET_KEY": "x" * 40,
    "STAFF_PASSWORD": "correct-horse-battery",
    "GEMINI_API_KEY": "test-key",
    "GEMINI_API_BASE": f"http://127.0.0.1:{_gemini_srv.server_address[1]}",
    "LLAMA_URL": f"http://127.0.0.1:{_llama_srv.server_address[1]}/v1/chat/completions",
    "WHATSAPP_VERIFY_TOKEN": "verify-me",
    "WHATSAPP_ACCESS_TOKEN": "wa-token",
    "WHATSAPP_PHONE_NUMBER_ID": "12345",
    "WHATSAPP_APP_SECRET": "app-secret",
    "TRUST_PROXY_HOPS": "0",
})
os.environ.pop("REDIS_URL", None)
os.environ.pop("DATABASE_URL", None)

from noah import llm, sessions  # noqa: E402
from noah.limiter import limiter  # noqa: E402
from noah.store import reset_store  # noqa: E402


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    _State.reset()
    llm.reset_state()
    limiter.reset()
    sessions._mem.clear()
    store = reset_store(str(tmp_path / "t.db"))
    yield store


@pytest.fixture
def fake():
    return _State


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def staff_headers(client):
    token = client.post("/api/staff/login", json={"password": "correct-horse-battery"}).json["token"]
    return {"Authorization": f"Bearer {token}"}
