"""Guards for static/widget.js, the single file the college site loads."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WIDGET = Path(__file__).resolve().parent.parent / "static" / "widget.js"
SRC = WIDGET.read_text(encoding="utf-8")


def test_widget_is_valid_javascript():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    result = subprocess.run([node, "--check", str(WIDGET)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_widget_has_no_emoji():
    emoji = [c for c in SRC if ord(c) >= 0x1F000 or 0x2600 <= ord(c) <= 0x27BF]
    assert not emoji, f"emoji found: {emoji[:5]}"


def test_native_append_is_never_used_with_nullable_children():
    # Element.append(null) prints the text "null" and append([..]) prints "[object ...]". Use put().
    assert ".append(" not in SRC


def test_every_api_path_the_widget_calls_exists_on_the_server(client):
    import app as app_module
    adapter = app_module.app.url_map.bind("localhost")
    paths = set(re.findall(r"'(/(?:api|predict)[^'?]*)", SRC))
    static_paths = {p for p in paths if not p.endswith("/")}
    missing = []
    for path in sorted(static_paths):
        found = False
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            try:
                adapter.match(path, method=method)
                found = True
                break
            except Exception:  # noqa: BLE001 - NotFound / MethodNotAllowed
                continue
        if not found:
            missing.append(path)
    assert not missing, f"widget calls endpoints the server does not have: {missing}"
    assert len(static_paths) >= 20


def test_dynamic_staff_routes_exist():
    import app as app_module
    adapter = app_module.app.url_map.bind("localhost")
    for path, method in (("/api/staff/unanswered/5/answer", "POST"), ("/api/staff/unanswered/5/dismiss", "POST"), ("/api/staff/learned/3", "DELETE"),
                         ("/api/staff/leads/2", "PATCH"), ("/api/staff/student-codes/4", "DELETE"), ("/api/staff/events/some-id", "DELETE")):
        adapter.match(path, method=method)


def test_widget_served_with_cache_header(client):
    r = client.get("/widget.js")
    assert r.status_code == 200 and "max-age" in r.headers["Cache-Control"]
    assert r.mimetype in ("text/javascript", "application/javascript")


def test_widget_never_embeds_a_secret():
    # Names of settings may appear in help text; actual key material must not.
    assert not re.search(r"AIza[0-9A-Za-z_\-]{20,}", SRC)
    assert not re.search(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]", SRC)
