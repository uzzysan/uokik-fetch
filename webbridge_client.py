"""
Python client for Kimi WebBridge daemon.

Provides a simple wrapper around the local WebBridge HTTP API
(http://127.0.0.1:10086/command) so that scrapers can use a real browser
instead of raw requests (required for sites protected by WAF / JS challenges).
"""
import json
import time
import requests
from typing import Optional, Dict, Any

WEBBRIDGE_URL = "http://127.0.0.1:10086/command"
DEFAULT_SESSION = "uokik-scraper"


def _send_command(action: str, args: dict, session: str = DEFAULT_SESSION) -> dict:
    """Send a command to the WebBridge daemon and return the parsed response."""
    payload = {
        "action": action,
        "args": args,
        "session": session,
    }
    try:
        resp = requests.post(
            WEBBRIDGE_URL,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"WebBridge error: {data.get('error', 'unknown')}")
        return data.get("data", {})
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            f"Cannot connect to WebBridge daemon at {WEBBRIDGE_URL}. "
            f"Please start it first: {e}"
        )


def navigate(url: str, new_tab: bool = True, group_title: Optional[str] = None, session: str = DEFAULT_SESSION) -> dict:
    """Navigate to a URL in the browser."""
    args = {"url": url, "newTab": new_tab}
    if group_title:
        args["group_title"] = group_title
    return _send_command("navigate", args, session)


def find_tab(url: str, session: str = DEFAULT_SESSION) -> dict:
    """Find an existing tab by URL."""
    return _send_command("find_tab", {"url": url}, session)


def snapshot(session: str = DEFAULT_SESSION) -> dict:
    """Take an accessibility snapshot of the current page."""
    return _send_command("snapshot", {}, session)


def click(selector: str, session: str = DEFAULT_SESSION) -> dict:
    """Click an element by @e ref or CSS selector."""
    return _send_command("click", {"selector": selector}, session)


def fill(selector: str, value: str, session: str = DEFAULT_SESSION) -> dict:
    """Fill an input / textarea / contenteditable element."""
    return _send_command("fill", {"selector": selector, "value": value}, session)


def evaluate(code: str, session: str = DEFAULT_SESSION) -> Any:
    """Execute JavaScript in the current page and return the result."""
    data = _send_command("evaluate", {"code": code}, session)
    return data.get("value")


def screenshot(path: Optional[str] = None, session: str = DEFAULT_SESSION) -> dict:
    """Take a screenshot of the current page."""
    args = {}
    if path:
        args["path"] = path
    return _send_command("screenshot", args, session)


def list_tabs(session: str = DEFAULT_SESSION) -> list:
    """List all tabs in the session."""
    data = _send_command("list_tabs", {}, session)
    return data.get("tabs", [])


def close_session(session: str = DEFAULT_SESSION) -> dict:
    """Close all tabs in the session."""
    return _send_command("close_session", {}, session)


def ensure_daemon_running() -> None:
    """Start the WebBridge daemon if it is not already running."""
    import subprocess
    import sys
    import os

    try:
        requests.post(WEBBRIDGE_URL, json={"action": "list_tabs", "args": {}}, timeout=2)
        return  # Daemon is already running
    except requests.exceptions.ConnectionError:
        pass

    # Try to start the daemon
    if sys.platform == "win32":
        exe = os.path.expanduser(r"~\.kimi-webbridge\bin\kimi-webbridge.exe")
        if os.path.exists(exe):
            subprocess.Popen([exe, "start"], creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            return
    else:
        exe = os.path.expanduser("~/.kimi-webbridge/bin/kimi-webbridge")
        if os.path.exists(exe):
            subprocess.Popen([exe, "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
            return

    raise RuntimeError(
        "WebBridge daemon is not running and could not be auto-started. "
        "Please start it manually."
    )
