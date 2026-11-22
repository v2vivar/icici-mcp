"""Shared authentication module for ICICI Direct MCP server."""

import asyncio
import json
import logging
import os
import sys
import tempfile
import webbrowser
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

import pyotp
from breeze_connect import BreezeConnect

TOKEN_FILE = Path.home() / ".icici_direct_token.json"
INDIA_TIME = timezone(timedelta(hours=5, minutes=30))


def _setup_logger():
    logger = logging.getLogger("icici_mcp")
    if not logger.handlers:
        handler = RotatingFileHandler(
            Path.home() / ".icici-mcp.log", maxBytes=5*1024*1024, backupCount=3
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger


logger = _setup_logger()


def load_credentials() -> dict:
    """Load credentials from environment variables.

    Returns a dict with keys: api_key, api_secret, user_id, password, totp_secret, session_token.
    API key and secret are required. Raises SystemExit if either is missing.
    """
    required = {
        "ICICI_API_KEY": "api_key",
        "ICICI_API_SECRET": "api_secret",
    }
    creds = {}
    missing = []

    for env_var, key in required.items():
        val = os.environ.get(env_var)
        if not val:
            missing.append(env_var)
        creds[key] = val or ""

    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        print(
            f"Error: Missing required environment variables: {', '.join(missing)}\n"
            "Set them in your shell or in your MCP client's env config.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    creds["totp_secret"] = os.environ.get("ICICI_TOTP_SECRET")
    creds["session_token"] = os.environ.get("ICICI_SESSION_TOKEN")
    creds["user_id"] = os.environ.get("ICICI_USER_ID", "")
    creds["password"] = os.environ.get("ICICI_PASSWORD", "")
    logger.debug("Credentials loaded for user_id=%s", creds["user_id"])
    return creds


def get_cached_token() -> str | None:
    """Return today's cached session token, or None if expired/missing."""
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text())
        if data.get("date") == datetime.now(INDIA_TIME).strftime("%Y-%m-%d"):
            logger.debug("Using cached session token from %s", data["date"])
            return data["session_token"]
        logger.debug("Cached token expired (date=%s)", data.get("date"))
    return None


def get_login_url(api_key: str) -> str:
    """Return the ICICI Direct login URL for the given API key."""
    encoded_key = quote_plus(api_key)
    return f"https://api.icicidirect.com/apiuser/login?api_key={encoded_key}"


def open_login_page(api_key: str) -> str:
    """Open the ICICI Direct login page in the default browser and return the URL."""
    url = get_login_url(api_key)
    webbrowser.open(url)
    return url


def save_session_token(session_token: str) -> None:
    """Cache a session token for the rest of the day."""
    fd, temporary_name = tempfile.mkstemp(dir=TOKEN_FILE.parent, prefix=".icici-token-")
    try:
        with os.fdopen(fd, "w") as token_file:
            json.dump(
                {
                    "session_token": session_token,
                    "date": datetime.now(INDIA_TIME).strftime("%Y-%m-%d"),
                },
                token_file,
            )
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, TOKEN_FILE)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    logger.info("Session token cached to %s", TOKEN_FILE)


def automated_login(
    api_key: str,
    api_secret: str,
    user_id: str,
    password: str,
    totp_secret: str,
) -> str:
    """Full automated login using headless Chromium via Playwright.

    Navigates the ICICI Direct login page, fills credentials, submits TOTP,
    and intercepts the redirect to extract the apisession token.

    Returns the session_token and saves it to TOKEN_FILE.
    """

    logger.info("Starting automated login for user_id=%s", user_id)

    async def _login() -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            logger.error("Playwright not installed: %s", e)
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from e

        login_url = get_login_url(api_key)
        apisession = None
        browser = None

        try:
            async with async_playwright() as p:
                logger.debug("Launching headless Chromium via Playwright")
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Intercept requests to capture apisession from redirect URL
                def on_request(request):
                    nonlocal apisession
                    try:
                        url = request.url
                        if "apisession" in url:
                            parsed = urlparse(url)
                            params = parse_qs(parsed.query)
                            token = params.get("apisession", [None])[0]
                            if token:
                                apisession = token
                                logger.info("Captured apisession token from redirect")
                    except Exception:
                        pass  # Don't crash on request parsing errors

                page.on("request", on_request)

                # Step 1: Navigate to login page (30s timeout)
                await page.goto(login_url, wait_until="networkidle", timeout=30000)

                # Step 2: Fill credentials
                uid_field = await page.query_selector("#txtuid")
                if not uid_field:
                    logger.error("Login page structure changed: #txtuid not found")
                    raise RuntimeError(
                        "Login page structure changed — #txtuid field not found. "
                        "ICICI Direct may have updated their login page."
                    )
                await page.fill("#txtuid", user_id)
                await page.fill("#txtPass", password)
                await page.check("#chkssTnc")

                # Step 3: Click login
                await page.click("#btnSubmit")
                await page.wait_for_timeout(3000)

                # Step 4: Enter TOTP
                totp_code = pyotp.TOTP(totp_secret).now()
                logger.debug("Generated TOTP code for submission")
                otp_inputs = await page.query_selector_all("input[tg-nm=otp]")

                if not otp_inputs:
                    # Check if login failed (wrong credentials)
                    error_el = await page.query_selector(".text-danger, #errmsg, .error")
                    if error_el:
                        error_text = await error_el.inner_text()
                        logger.error("Login failed with error: %s", error_text.strip())
                        raise RuntimeError(f"Login failed: {error_text.strip()}")
                    raise RuntimeError(
                        "OTP input fields not found after login. "
                        "Credentials may be wrong or login page changed."
                    )

                if len(otp_inputs) == 6:
                    for i, digit in enumerate(totp_code):
                        await otp_inputs[i].fill(digit)
                else:
                    await otp_inputs[0].fill(totp_code)

                # Step 5: Submit OTP
                try:
                    await page.evaluate("submitotp()")
                except Exception as e:
                    print(f"Warning: submitotp() JS call failed: {e}", file=sys.stderr)
                    # Try clicking a submit button as fallback
                    submit_btn = await page.query_selector("#btnOTP, button[type=submit]")
                    if submit_btn:
                        await submit_btn.click()

                await page.wait_for_timeout(5000)

                await browser.close()
                browser = None

        except RuntimeError:
            raise  # Re-raise our own errors
        except Exception as e:
            logger.error("Automated login failed: %s: %s", type(e).__name__, e)
            raise RuntimeError(
                f"Automated login failed: {type(e).__name__}: {e}\n"
                "Possible causes:\n"
                "- Chromium not installed: run 'playwright install chromium'\n"
                "- Network issue: check internet connection\n"
                "- ICICI login page changed: try 'icici-mcp-login' manually\n"
                "- TOTP expired: check ICICI_TOTP_SECRET is correct"
            ) from e
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

        if not apisession:
            logger.error("Could not extract apisession after login completed")
            raise RuntimeError(
                "Could not extract apisession after login completed. "
                "The redirect URL may not contain the token. "
                "Try running 'icici-mcp-login' to log in manually."
            )

        return apisession

    # Run the async login — handle both fresh and existing event loops
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context (e.g., MCP server) — use nest_asyncio or new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            session_token = pool.submit(asyncio.run, _login()).result()
    else:
        session_token = asyncio.run(_login())

    # Cache the token
    save_session_token(session_token)

    return session_token


def get_authenticated_breeze(creds: dict, *, use_cached_token: bool = True) -> BreezeConnect:
    """Return an authenticated BreezeConnect instance.

    Auth priority:
    1. Today's cached session token
    2. ICICI_SESSION_TOKEN env var (manual override)
    3. Error with instructions for manual login
    """
    logger.info("Authenticating with ICICI Direct for user_id=%s", creds["user_id"])
    breeze = BreezeConnect(api_key=creds["api_key"])

    # Try cached token first — validate it actually works
    cached = get_cached_token() if use_cached_token else None
    if cached:
        try:
            breeze.generate_session(
                api_secret=creds["api_secret"], session_token=cached
            )
            # Breeze validates the API session during generate_session.
            logger.info("Authenticated using cached token")
            return breeze
        except Exception as e:
            # Cached token is invalid/expired — fall through to other methods
            logger.warning("Cached token invalid: %s", e)
            print("Cached ICICI token invalid, checking manual session token...", file=sys.stderr)
            breeze = BreezeConnect(api_key=creds["api_key"])

    # Try manual session token override
    if creds["session_token"]:
        try:
            breeze.generate_session(
                api_secret=creds["api_secret"],
                session_token=creds["session_token"],
            )
        except Exception as e:
            logger.warning("Manual session token validation failed: %s", e)
            raise RuntimeError("Manual ICICI session token could not be validated.") from e
        save_session_token(creds["session_token"])
        logger.info("Authenticated using manual session token")
        return breeze

    # No valid token available
    logger.error("No valid session token available")
    raise RuntimeError(
        "No valid session token. Run icici-mcp-login in the same environment, "
        "or set ICICI_SESSION_TOKEN to a manually obtained API session token."
    )
