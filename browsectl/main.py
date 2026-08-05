"""CLI entry point and wiring."""

import asyncio
import sys
from enum import StrEnum

from browsectl.adapters import cdp
from browsectl.core import dispatch
from browsectl.gateway import BrowserGateway
from browsectl.models import Command

USAGE = """\
Usage: browsectl -s <session> [-b <backend>] <command> [args...]

Options:
  -s, --session <name>    Named session (REQUIRED)
  -b, --backend <name>    Browser backend (default: cdp)
                          Available: cdp

Commands:
  launch [port] [--host h] [--timeout s] [--foreground]
                          Launch Chrome and connect (auto-assigns port if omitted)
                          Default: runs in Xvfb virtual display (no visible window)
                          --foreground: show the browser window on screen
  stop                    Stop a launched Chrome session
  stop-all                Stop all sessions and kill their processes
  sessions [--prune]      List all saved sessions (--prune removes stale ones)
  profiles [--prune]      List all profile directories (--prune removes orphaned ones)
  connect <host> <port>   Connect to an existing browser at host:port
  goto <url>              Navigate to URL
  screenshot [path]       Save screenshot (default: screenshot.png)
  click <selector>        Click element by CSS selector
  click-xy <x> <y>       Click at viewport coordinates
  click-text <text>      Click first element matching visible text
  drag <x1> <y1> <x2> <y2>  Drag from (x1,y1) to (x2,y2)
  hover <selector>       Move mouse over element (triggers :hover CSS, tooltips)
  type <selector> <text>  Type text into element
  html <selector>         Extract innerHTML of element
  eval <expression>       Evaluate JavaScript expression
  info                    Show current page URL and title
  tabs                    List open tabs
  newtab [url]            Open a new tab (default: about:blank)
  switchtab <tab-id>      Switch to a tab by ID (from 'tabs' output)
  scroll <pixels>         Scroll page (positive=down, negative=up)
  resize <width> <height> Set viewport dimensions (for responsive testing)
  wait <selector> [timeout]  Wait for element to appear (default: 30s)
  clear-cookies             Clear all browser cookies for this session
"""


class Backend(StrEnum):
    CDP = "cdp"


def _build_cdp_gateway() -> BrowserGateway[cdp.CdpSession]:
    return BrowserGateway(
        connect=cdp.connect,
        disconnect=cdp.disconnect,
        navigate=cdp.navigate,
        screenshot=cdp.screenshot,
        click=cdp.click,
        click_xy=cdp.click_xy,
        hover=cdp.hover,
        click_text=cdp.click_text,
        drag=cdp.drag,
        type_text=cdp.type_text,
        extract_html=cdp.extract_html,
        eval_js=cdp.eval_js,
        page_info=cdp.page_info,
        list_tabs=cdp.list_tabs,
        new_tab=cdp.new_tab,
        switch_tab=cdp.switch_tab,
        scroll=cdp.scroll,
        resize=cdp.resize,
        wait_for=cdp.wait_for,
        clear_cookies=cdp.clear_cookies,
        launch_browser=cdp.launch_browser,
        configure_browser=cdp.configure_browser,
    )


def _parse_args(
    argv: list[str],
) -> tuple[Backend, str, Command, tuple[str, ...]]:
    backend = Backend.CDP
    session_name: str | None = None
    args = list(argv)

    while args and args[0].startswith("-"):
        flag = args.pop(0)
        if flag in ("-b", "--backend"):
            if not args:
                raise SystemExit("--backend requires a value")
            try:
                backend = Backend(args.pop(0))
            except ValueError as e:
                raise SystemExit(
                    f"Unknown backend: {e}. "
                    f"Available: {', '.join(Backend)}"
                )
        elif flag in ("-s", "--session"):
            if not args:
                raise SystemExit("--session requires a value")
            session_name = args.pop(0)
        elif flag in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        else:
            print(f"Unknown flag: {flag}", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            raise SystemExit(1)

    if not args:
        print(USAGE)
        raise SystemExit(0)

    try:
        command = Command(args[0])
    except ValueError:
        print(f"Unknown command: {args[0]}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        raise SystemExit(1)

    no_session_commands = {Command.SESSIONS, Command.STOP_ALL, Command.PROFILES}
    if session_name is None and command not in no_session_commands:
        raise SystemExit(
            "Missing required option: -s <session>\n"
            "Every command requires a named session.\n"
            "Example: browsectl -s mysession info"
        )

    return backend, session_name or "", command, tuple(args[1:])


def main() -> None:
    """Entry point for the browsectl CLI."""
    backend, session_name, command, args = _parse_args(sys.argv[1:])
    match backend:
        case Backend.CDP:
            gateway = _build_cdp_gateway()
        case _:
            raise SystemExit(f"Unsupported backend: {backend}")
    output = asyncio.run(dispatch(gateway, command, args, session_name))
    if output:
        print(output)
