"""Noah's data must live on the persistent disk. On Render the disk can be mounted at /var/data/staff, while a plain /var/data
folder exists on the container's temporary filesystem and is wiped at every restart: choosing it lost every lead and every edit."""

from pathlib import Path

from noah import config
from noah.store import Store


def fake_fs(folders, mounts, unwritable=()):
    return dict(exists=lambda p: p in folders, ismount=lambda p: p in mounts, writable=lambda p: p not in unwritable)


def test_render_case_disk_mounted_at_var_data_staff_beats_the_plain_var_data_folder():
    # /var/data is an ordinary, writable folder (root can write anywhere) - but the real disk is /var/data/staff
    fs = fake_fs(folders={"/var/data", "/var/data/staff"}, mounts={"/var/data/staff"})
    assert config.find_data_dir(children=lambda p: ["/var/data/staff"], **fs) == ("/var/data/staff", "disk")


def test_disk_mounted_directly_at_var_data():
    fs = fake_fs(folders={"/var/data"}, mounts={"/var/data"})
    assert config.find_data_dir(children=lambda p: [], **fs) == ("/var/data", "disk")


def test_disk_mounted_under_any_name_inside_var_data():
    fs = fake_fs(folders={"/var/data", "/var/data/noah-disk"}, mounts={"/var/data/noah-disk"})
    assert config.find_data_dir(children=lambda p: ["/var/data/noah-disk"], **fs) == ("/var/data/noah-disk", "disk")


def test_a_plain_folder_is_used_but_not_claimed_to_be_persistent():
    fs = fake_fs(folders={"/var/data"}, mounts=set())
    assert config.find_data_dir(children=lambda p: [], **fs) == ("/var/data", "folder")


def test_unwritable_mounts_are_skipped():
    fs = fake_fs(folders={"/var/data/staff", "/var/data"}, mounts={"/var/data/staff"}, unwritable={"/var/data/staff"})
    assert config.find_data_dir(children=lambda p: ["/var/data/staff"], **fs) == ("/var/data", "folder")


def test_nothing_found_means_the_project_folder_is_used():
    assert config.find_data_dir(children=lambda p: [], **fake_fs(folders=set(), mounts=set())) == (None, "none")


def test_an_explicit_data_dir_wins():
    assert config.find_data_dir("/somewhere/else", children=lambda p: [], **fake_fs(folders={"/var/data/staff"}, mounts={"/var/data/staff"})) == ("/somewhere/else", "explicit")


def test_is_on_mount_recognises_files_on_a_mounted_disk():
    mounts = {Path("/var/data/staff")}                       # Path equality, so the test behaves the same on Windows and Linux
    assert config.is_on_mount("/var/data/staff/noah.db", ismount=lambda p: Path(p) in mounts)
    assert not config.is_on_mount("/var/data/noah.db", ismount=lambda p: Path(p) in mounts)       # the temporary folder next to it
    assert not config.is_on_mount("/noah.db", ismount=lambda p: True)                         # "/" itself tells us nothing


def test_default_db_path_uses_the_found_disk(monkeypatch):
    monkeypatch.delenv("NOAH_DB_PATH", raising=False)
    monkeypatch.setattr(config, "find_data_dir", lambda explicit="": ("/var/data/staff", "disk"))
    assert config.default_db_path() == str(Path("/var/data/staff") / "noah.db")


def test_noah_db_path_always_wins(monkeypatch):
    monkeypatch.setenv("NOAH_DB_PATH", "/var/data/staff/noah.db")
    assert config.default_db_path() == "/var/data/staff/noah.db"


def test_storage_info_kinds(monkeypatch):
    monkeypatch.setenv("NOAH_DB_PATH", "/var/data/staff/noah.db")
    monkeypatch.setattr(config, "is_on_mount", lambda p, **kw: True)
    assert config.storage_info() == {"kind": "disk", "path": "/var/data/staff/noah.db", "persistent": True}
    monkeypatch.setattr(config, "is_on_mount", lambda p, **kw: False)
    assert config.storage_info()["kind"] == "folder" and config.storage_info()["persistent"] is False
    monkeypatch.setenv("NOAH_DB_PATH", str(config.ROOT / "noah.db"))
    assert config.storage_info()["kind"] == "local"


def test_health_and_dashboard_report_the_storage(client, staff_headers):
    assert client.get("/api/health").json["storage"] in ("disk", "folder", "local")
    s = client.get("/api/staff/overview", headers=staff_headers).json["storage"]
    assert set(s) == {"kind", "path", "persistent"} and isinstance(s["persistent"], bool)


def test_a_restart_keeps_everything(tmp_path):
    """What a persistent disk gives you: a second process opening the same file sees all the data."""
    path = str(tmp_path / "noah.db")
    first = Store(path)
    lead_id = first.add_lead("callback", name="Asha Rao", phone="9876543210", consent=True)
    first.add_learned("What is the canteen menu?", "A fixed vegetarian menu.")
    code = first.create_student_code("II PUC PCMB", "II PUC")
    first.upsert_event({"id": "mun", "title": "CJC MUN", "starts": "2026-11-21"})
    del first
    second = Store(path)                                                      # the server restarted
    assert [l["id"] for l in second.list_leads()] == [lead_id]
    assert second.list_learned()[0]["answer"] == "A fixed vegetarian menu."
    assert second.verify_student_code(code)["label"] == "II PUC PCMB"
    assert {e["id"]: e for e in second.list_events()}["mun"]["starts"] == "2026-11-21"


def test_widget_shows_the_storage_line_and_start_script_protects_the_disk():
    root = Path(__file__).resolve().parent.parent
    src = (root / "static" / "widget.js").read_text(encoding="utf-8")
    assert "kv('Data storage'" in src and "d.storage.persistent" in src and "NOAH_DB_PATH" in src
    sh = (root / "start.sh").read_text(encoding="utf-8")
    assert "/var/data/staff" in sh and "-gt 4000000" in sh and "/tmp/models" in sh      # the 1 GB model only goes on the disk with room to spare
