from __future__ import annotations

from app.reports.mailer import send_report


def _set_settings(**kwargs):
    from app.config import settings
    old = {name: getattr(settings, name) for name in kwargs}
    for name, value in kwargs.items():
        object.__setattr__(settings, name, value)
    return settings, old


def _restore(settings, old):
    for name, value in old.items():
        object.__setattr__(settings, name, value)


def test_mailer_skips_when_send_email_false():
    settings, old = _set_settings(send_email=False)
    try:
        assert send_report("subject", "<b>html</b>") is False
    finally:
        _restore(settings, old)


def test_mailer_rejects_unknown_provider():
    settings, old = _set_settings(send_email=True, email_provider="unknown")
    try:
        try:
            send_report("subject", "<b>html</b>")
        except RuntimeError as exc:
            assert "Unsupported EMAIL_PROVIDER" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError")
    finally:
        _restore(settings, old)
