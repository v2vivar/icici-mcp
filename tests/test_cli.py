"""Tests for the CLI module."""

import os
from unittest import mock

import pytest

from icici_mcp.cli import login, status


class TestLogin:
    """Tests for the login CLI command."""

    def test_exits_with_empty_session_input(self):
        env = {
            "ICICI_API_KEY": "key",
            "ICICI_API_SECRET": "secret",
            "ICICI_USER_ID": "AB1234",
            "ICICI_PASSWORD": "pass",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("icici_mcp.cli.getpass", return_value=""):
                with pytest.raises(SystemExit):
                    login()

    def test_manual_login_validates_entered_token_not_cached_token(self):
        env = {"ICICI_API_KEY": "key", "ICICI_API_SECRET": "secret"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("icici_mcp.cli.getpass", return_value="new-token"):
                with mock.patch("icici_mcp.cli.get_authenticated_breeze") as authenticate:
                    login()
        assert authenticate.call_args.kwargs == {"use_cached_token": False}
        assert authenticate.call_args.args[0]["session_token"] == "new-token"


class TestStatus:
    """Tests for the status CLI command."""

    def test_exits_when_no_token(self, tmp_path):
        token_file = tmp_path / "nonexistent.json"
        with mock.patch("icici_mcp.auth.TOKEN_FILE", token_file):
            with pytest.raises(SystemExit):
                status()
