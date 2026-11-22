"""CLI entry points for icici-mcp."""

import sys
from getpass import getpass

from icici_mcp.auth import (
    get_authenticated_breeze,
    get_cached_token,
    get_login_url,
    load_credentials,
)


def login():
    """Log in to ICICI Direct and cache the session token."""
    creds = load_credentials()

    # If session token is provided via env, use it directly
    if creds["session_token"]:
        get_authenticated_breeze(creds, use_cached_token=False)
        print("Login successful using session token. Cached for today.")
        return

    # Otherwise, display the login URL and ask for the session token.
    url = get_login_url(creds["api_key"])
    print(f"Open this login page in your browser: {url}\n")
    print("After logging in, copy the 'apisession' value from the redirect URL.")
    session_token = getpass("Paste your apisession here (hidden): ").strip()

    if not session_token:
        print("Error: No session token provided.", file=sys.stderr)
        sys.exit(1)

    # Validate by connecting
    get_authenticated_breeze({**creds, "session_token": session_token}, use_cached_token=False)
    print("Login successful. Session token cached for today.")


def status():
    """Check if a valid cached token exists."""
    cached = get_cached_token()
    if cached:
        print("A session token is cached for today; its broker validity has not been checked.")
    else:
        print(
            "No valid token. Run 'icici-mcp-login' to log in, "
            "or set ICICI_SESSION_TOKEN."
        )
        sys.exit(1)
