"""Email alerts and .env loading. SMTP is faked: no test here can send real mail or read a real .env."""

import pytest

from noah import config, notify


class FakeSMTP:
    sessions = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.log, self.sent = host, port, [], []
        FakeSMTP.sessions.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.log.append("ehlo")

    def starttls(self):
        self.log.append("starttls")

    def login(self, user, password):
        self.log.append(("login", user, password))

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sessions = []
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    for name, value in dict(SMTP_HOST="smtp.gmail.com", SMTP_PORT=587, SMTP_USER="sender@example.com", SMTP_PASSWORD="app-pass",
                            SMTP_FROM="sender@example.com", SMTP_FROM_NAME="CogniAI Studios",
                            ADMISSIONS_EMAIL="office@example.edu", COUNSELLING_EMAIL="counsel@example.edu", NOTIFY_WEBHOOK_URL="").items():
        monkeypatch.setattr(config, name, value)
    return FakeSMTP


def test_lead_email_goes_to_the_office_from_the_named_sender(smtp):
    notify.lead_created("callback", {"id": "CJC-C00001", "name": "Asha Rao", "phone": "9876543210", "interest": "ibdp"}).join(5)
    session = smtp.sessions[0]
    assert (session.host, session.port) == ("smtp.gmail.com", 587)
    assert session.log == ["ehlo", "starttls", "ehlo", ("login", "sender@example.com", "app-pass")]
    msg = session.sent[0]
    assert msg["From"] == "CogniAI Studios <sender@example.com>"
    assert msg["To"] == "office@example.edu"
    assert msg["Subject"] == "[Noah] New callback request"
    body = msg.get_content()
    assert "Asha Rao" in body and "9876543210" in body and "CJC-C00001" in body


def test_counselling_requests_use_the_counselling_address(smtp):
    notify.lead_created("counselling", {"id": "CJC-C00002", "name": "Ravi", "phone": "9123456780"}).join(5)
    assert smtp.sessions[0].sent[0]["To"] == "counsel@example.edu"


def test_plain_sender_when_no_name_is_set(smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_FROM_NAME", "")
    notify.lead_created("visit", {"id": "CJC-V00001", "name": "Ravi", "phone": "9123456780"}).join(5)
    assert smtp.sessions[0].sent[0]["From"] == "sender@example.com"


def test_nothing_is_sent_when_smtp_is_not_configured(smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    notify.lead_created("callback", {"id": "CJC-C00003", "name": "Asha Rao", "phone": "9876543210"}).join(5)
    assert smtp.sessions == []


def test_a_broken_mail_server_never_raises(smtp, monkeypatch):
    def boom(self, user, password):
        raise OSError("535 bad credentials")
    monkeypatch.setattr(FakeSMTP, "login", boom)
    notify.lead_created("callback", {"id": "CJC-C00004", "name": "Asha Rao", "phone": "9876543210"}).join(5)   # must not raise


# ---- .env loading -------------------------------------------------------------------------------------------
def test_dotenv_loads_values_comments_and_quotes_but_never_overrides_real_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "T_PLAIN=hello\n"
        "T_INLINE=value   # trailing comment\n"
        "T_QUOTED=\"two words # not a comment\"\n"
        "export T_EXPORT=yes\n"
        "T_EMPTY=\n"
        "T_REAL=from-file\n", encoding="utf-8")
    for key in ("T_PLAIN", "T_INLINE", "T_QUOTED", "T_EXPORT", "T_EMPTY", "T_REAL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("T_REAL", "from-environment")
    monkeypatch.delenv("NOAH_SKIP_DOTENV", raising=False)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    config._load_dotenv()
    import os
    assert os.environ["T_PLAIN"] == "hello"
    assert os.environ["T_INLINE"] == "value"
    assert os.environ["T_QUOTED"] == "two words # not a comment"
    assert os.environ["T_EXPORT"] == "yes"
    assert "T_EMPTY" not in os.environ
    assert os.environ["T_REAL"] == "from-environment"


def test_an_empty_variable_on_the_host_does_not_block_the_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("T_BLANK=from-file\n", encoding="utf-8")
    monkeypatch.setenv("T_BLANK", "")                      # e.g. a host that lists the variable with no value
    monkeypatch.delenv("NOAH_SKIP_DOTENV", raising=False)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    config._load_dotenv()
    import os
    assert os.environ["T_BLANK"] == "from-file"


def test_dotenv_is_skipped_under_tests(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("T_SKIPPED=1\n", encoding="utf-8")
    monkeypatch.delenv("T_SKIPPED", raising=False)
    monkeypatch.setenv("NOAH_SKIP_DOTENV", "1")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    config._load_dotenv()
    import os
    assert "T_SKIPPED" not in os.environ


def test_empty_environment_value_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("T_MODEL", "")
    assert config.env("T_MODEL", "gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"
