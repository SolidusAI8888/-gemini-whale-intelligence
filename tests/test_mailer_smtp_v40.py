from types import SimpleNamespace

from app.reports import mailer


def test_empty_smtp_host_falls_back_to_icloud(monkeypatch):
    monkeypatch.setattr(
        mailer,
        "settings",
        SimpleNamespace(smtp_host="", email_provider="smtp"),
    )

    assert mailer._smtp_host() == "smtp.mail.me.com"


def test_explicit_smtp_host_is_preserved(monkeypatch):
    monkeypatch.setattr(
        mailer,
        "settings",
        SimpleNamespace(smtp_host="smtp.example.com", email_provider="smtp"),
    )

    assert mailer._smtp_host() == "smtp.example.com"
