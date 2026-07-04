"""CLI entry point and wiring."""

import asyncio
import sys
from enum import StrEnum

from browsectl.adapters import cdp
from browsectl.core import dispatch
from browsectl.gateway import BrowserGateway
from browsectl.models import Command

USAGE = """\
Usage: browsectl [-b <backend>] [-s <session>] <command> [args...]

Options:
  -b, --backend <name>    Browser backend (default: cdp)
                          Available: cdp
  -s, --session <name>    Named session (default: default)
                          Allows multiple independent browser sessions

Commands:
  connect [host] [port]   Connect to browser (default: localhost:9222)
  goto <url>              Navigate to URL
  screenshot [path]       Save screenshot (default: screenshot.png)
  click <selector>        Click element by CSS selector
  type <selector> <text>  Type text into element
  html <selector>         Extract innerHTML of element
  eval <expression>       Evaluate JavaScript expression
  info                    Show current page URL and title
  tabs                    List open tabs
  newtab [url]            Open a new tab (default: about:blank)
  switchtab <tab-id>      Switch to a tab by ID (from 'tabs' output)
  scroll <pixels>         Scroll page (positive=down, negative=up)
  wait <selector> [timeout]  Wait for element to appear (default: 30s)
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
        type_text=cdp.type_text,
        extract_html=cdp.extract_html,
        eval_js=cdp.eval_js,
        page_info=cdp.page_info,
        list_tabs=cdp.list_tabs,
        new_tab=cdp.new_tab,
        switch_tab=cdp.switch_tab,
        scroll=cdp.scroll,
        wait_for=cdp.wait_for,
    )


def _parse_args(
    argv: list[str],
) -> tuple[Backend, str, Command, tuple[str, ...]]:
    backend = Backend.CDP
    session_name = "default"
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

    return backend, session_name, command, tuple(args[1:])


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
