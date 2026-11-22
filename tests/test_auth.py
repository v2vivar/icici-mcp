"""Tests for the auth module."""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from icici_mcp.auth import INDIA_TIME, get_cached_token, load_credentials, get_authenticated_breeze


class TestLoadCredentials:
    """Tests for load_credentials()."""

    def test_only_api_key_and_secret_are_required(self):
        env = {"ICICI_API_KEY": "test-key", "ICICI_API_SECRET": "test-secret"}
        with mock.patch.dict(os.environ, env, clear=True):
            creds = load_credentials()
        assert creds["api_key"] == "test-key"
        assert creds["api_secret"] == "test-secret"

    def test_loads_all_credentials(self):
        env = {
            "ICICI_API_KEY": "test-key",
            "ICICI_API_SECRET": "test-secret",
            "ICICI_USER_ID": "AB1234",
            "ICICI_PASSWORD": "testpass",
            "ICICI_TOTP_SECRET": "TOTP123",
            "ICICI_SESSION_TOKEN": "session-abc",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            creds = load_credentials()
            assert creds["api_key"] == "test-key"
            assert creds["api_secret"] == "test-secret"
            assert creds["user_id"] == "AB1234"
            assert creds["password"] == "testpass"
            assert creds["totp_secret"] == "TOTP123"
            assert creds["session_token"] == "session-abc"

    def test_totp_secret_is_optional(self):
        env = {
            "ICICI_API_KEY": "test-key",
            "ICICI_API_SECRET": "test-secret",
            "ICICI_USER_ID": "AB1234",
            "ICICI_PASSWORD": "testpass",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            # Remove TOTP if it exists
            os.environ.pop("ICICI_TOTP_SECRET", None)
            os.environ.pop("ICICI_SESSION_TOKEN", None)
            creds = load_credentials()
            assert creds["totp_secret"] is None

    def test_session_token_is_optional(self):
        env = {
            "ICICI_API_KEY": "test-key",
            "ICICI_API_SECRET": "test-secret",
            "ICICI_USER_ID": "AB1234",
            "ICICI_PASSWORD": "testpass",
            "ICICI_TOTP_SECRET": "TOTP123",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("ICICI_SESSION_TOKEN", None)
            creds = load_credentials()
            assert creds["session_token"] is None

    def test_exits_on_missing_required(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit):
                load_credentials()

    def test_exits_on_partial_credentials(self):
        env = {"ICICI_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit):
                load_credentials()


class TestGetCachedToken:
    """Tests for get_cached_token()."""

    def test_returns_token_for_today(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({
            "session_token": "test-token-123",
            "date": datetime.now(INDIA_TIME).strftime("%Y-%m-%d"),
        }))
        with mock.patch("icici_mcp.auth.TOKEN_FILE", token_file):
            assert get_cached_token() == "test-token-123"

    def test_returns_none_for_old_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({
            "session_token": "old-token",
            "date": "2020-01-01",
        }))
        with mock.patch("icici_mcp.auth.TOKEN_FILE", token_file):
            assert get_cached_token() is None

    def test_returns_none_when_file_missing(self, tmp_path):
        token_file = tmp_path / "nonexistent.json"
        with mock.patch("icici_mcp.auth.TOKEN_FILE", token_file):
            assert get_cached_token() is None


class TestPlaywrightImportError:
    def test_automated_login_fails_without_playwright(self):
        """If playwright is not installed, should raise RuntimeError."""
        import sys

        with mock.patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):
            # This test verifies the error message mentions playwright installation
            # Note: may need to reload the module or test differently
            pass  # Placeholder -- implement based on actual import structure


class TestManualAuthentication:
    def test_explicit_login_replaces_cached_token(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({
            "session_token": "old-token",
            "date": datetime.now(INDIA_TIME).strftime("%Y-%m-%d"),
        }))
        monkeypatch.setattr("icici_mcp.auth.TOKEN_FILE", token_file)
        breeze = mock.Mock()
        monkeypatch.setattr("icici_mcp.auth.BreezeConnect", lambda **kwargs: breeze)
        creds = {"api_key": "key", "api_secret": "secret", "user_id": "",
                 "session_token": "new-token", "totp_secret": None}

        get_authenticated_breeze(creds, use_cached_token=False)

        breeze.generate_session.assert_called_once_with(api_secret="secret", session_token="new-token")
        assert get_cached_token() == "new-token"
        breeze.reset_mock()
        get_authenticated_breeze({**creds, "session_token": None})
        breeze.generate_session.assert_called_once_with(api_secret="secret", session_token="new-token")

    def test_rejected_manual_token_does_not_replace_cache(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({
            "session_token": "old-token",
            "date": datetime.now(INDIA_TIME).strftime("%Y-%m-%d"),
        }))
        monkeypatch.setattr("icici_mcp.auth.TOKEN_FILE", token_file)
        breeze = mock.Mock()
        breeze.generate_session.side_effect = ValueError("Rejected")
        monkeypatch.setattr("icici_mcp.auth.BreezeConnect", lambda **kwargs: breeze)
        creds = {"api_key": "key", "api_secret": "secret", "user_id": "",
                 "session_token": "bad-token", "totp_secret": None}

        with pytest.raises(RuntimeError, match="could not be validated"):
            get_authenticated_breeze(creds, use_cached_token=False)
        assert get_cached_token() == "old-token"

    def test_no_automatic_login_even_with_totp_secret(self, monkeypatch, tmp_path):
        monkeypatch.setattr("icici_mcp.auth.TOKEN_FILE", tmp_path / "missing.json")
        monkeypatch.setattr("icici_mcp.auth.BreezeConnect", mock.Mock())
        automatic_login = mock.Mock()
        monkeypatch.setattr("icici_mcp.auth.automated_login", automatic_login)
        creds = {"api_key": "key", "api_secret": "secret", "user_id": "",
                 "session_token": None, "totp_secret": "unused"}

        with pytest.raises(RuntimeError, match="No valid session token"):
            get_authenticated_breeze(creds)
        automatic_login.assert_not_called()

    def test_token_cache_uses_india_calendar_day(self, monkeypatch, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"session_token": "token", "date": "2026-01-02"}))
        monkeypatch.setattr("icici_mcp.auth.TOKEN_FILE", token_file)
        clock = mock.Mock()
        clock.now.return_value = datetime(2026, 1, 2, 0, 1, tzinfo=INDIA_TIME)
        monkeypatch.setattr("icici_mcp.auth.datetime", clock)

        assert get_cached_token() == "token"
        clock.now.assert_called_once_with(INDIA_TIME)
        clock.now.return_value = datetime(2026, 1, 3, 0, 0, tzinfo=INDIA_TIME)
        assert get_cached_token() is None
