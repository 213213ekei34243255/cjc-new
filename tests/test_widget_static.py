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


def test_tools_sheet_can_never_cover_the_message_box():
    # Regression for the white band / "Tools will not close" bug: the closed sheet used to slide out of the chat area and sit over the composer.
    assert "$.sheet = h('div', { class: 'nw-sheet', hidden: true })" in SRC               # starts fully removed
    assert ".nw-body{position:relative;flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}" in SRC   # clips the slid-away sheet
    assert "visibility:hidden;pointer-events:none" in SRC                                  # closed sheet is invisible and unclickable
    assert ".nw-comp{position:relative;z-index:8;" in SRC and ".nw-foot{position:relative;z-index:8;" in SRC   # composer paints above any remnant
    assert "$.sheet.hidden = true" in SRC and "$.sheet.hidden = false" in SRC
    show = SRC[SRC.index("function showSheet()"):SRC.index("function hideSheet()")]
    assert "requestAnimationFrame" not in show and "setTimeout" not in show                # opening must not depend on frames or timers


def test_escape_closes_the_sheet_before_the_window():
    assert "if ($.sheet.classList.contains('open')) hideSheet(); else if ($.panel.classList.contains('open')) closePanel(); else close();" in SRC


def test_widget_reports_its_version():
    assert re.search(r"var VERSION = '\d{4}-\d{2}-\d{2}\.\d+';", SRC)
    assert "version: VERSION" in SRC and "Widget file version" in SRC


def test_footer_shows_the_build_number_and_health_reports_the_same_version(client):
    version = re.search(r"var VERSION = '([^']+)'", SRC).group(1)
    assert "' \\u00B7 build ' + VERSION.split('.').pop()" in SRC
    assert client.get("/api/health").json["widget"] == version


def test_widget_is_revalidated_on_every_load_by_default(client):
    assert client.get("/widget.js").headers["Cache-Control"] == "public, max-age=0"


def test_call_me_back_is_not_offered_in_the_tools_list():
    # The callback form still exists (chat and buttons can open it); only its tile was removed from the Tools list and welcome grid.
    assert "{ id: 'callback', icon: 'phone', key: 'callback', hue: '#1746d1', blurb: 'We call you back', tile: false }" in SRC
    assert "if (t.tile === false) return;" in SRC
    assert "PANELS.callback = function" in SRC
