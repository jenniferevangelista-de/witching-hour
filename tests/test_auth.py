from witching_hour import auth


def test_auth_is_off_without_settings(monkeypatch):
    for k in ("AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "SESSION_SECRET", "FAMILY_EMAILS"):
        monkeypatch.delenv(k, raising=False)
    assert auth.enabled() is False


def test_auth_needs_live_mode_and_every_setting(monkeypatch):
    for k, v in {"AUTH0_DOMAIN": "x.eu.auth0.com", "AUTH0_CLIENT_ID": "id", "AUTH0_CLIENT_SECRET": "s",
                 "SESSION_SECRET": "k", "FAMILY_EMAILS": "Ana@Example.com, bo@example.com"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("WH_LIVE", "1")
    assert auth.enabled() is True
    monkeypatch.setenv("WH_LIVE", "0")
    assert auth.enabled() is False  # the public demo never turns it on


def test_only_verified_allowlisted_emails_are_family(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", "Ana@Example.com, bo@example.com")
    assert auth.is_family({"email": "ana@example.com", "email_verified": True})
    assert not auth.is_family({"email": "ana@example.com", "email_verified": False})
    assert not auth.is_family({"email": "stranger@example.com", "email_verified": True})
    assert not auth.is_family({})
