"""Command orchestration -- browser-agnostic business logic."""

import json
import logging
from pathlib import Path

from browsectl.gateway import BrowserGateway
from browsectl.models import BrowserEndpoint, Command

logger = logging.getLogger(__name__)

SESSION_DIR = Path.home() / ".browsectl"
SESSION_FILE = SESSION_DIR / "session.json"
SCREENSHOT_PATH = Path("screenshot.png")


def load_endpoint() -> BrowserEndpoint:
    """Load the saved browser endpoint from the session file."""
    if not SESSION_FILE.exists():
        raise SystemExit(
            "No active session. Run: browsectl connect <host> <port>"
        )
    data = json.loads(SESSION_FILE.read_text())
    return BrowserEndpoint(host=data["host"], port=data["port"])


def save_endpoint(endpoint: BrowserEndpoint) -> None:
    """Save the browser endpoint to the session file."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(
        json.dumps({"host": endpoint.host, "port": endpoint.port})
    )


async def dispatch[S](
    gateway: BrowserGateway[S],
    command: Command,
    args: tuple[str, ...],
) -> str:
    """Dispatch a CLI command through the gateway. Returns output text."""
    if command == Command.CONNECT:
        host = args[0] if args else "localhost"
        port = int(args[1]) if len(args) > 1 else 9222
        endpoint = BrowserEndpoint(host=host, port=port)
        session = await gateway.connect(endpoint)
        await gateway.disconnect(session)
        save_endpoint(endpoint)
        return f"Connected to {host}:{port}"

    endpoint = load_endpoint()
    session = await gateway.connect(endpoint)
    try:
        return await _run_command(gateway, session, command, args)
    finally:
        await gateway.disconnect(session)


async def _run_command[S](
    gateway: BrowserGateway[S],
    session: S,
    command: Command,
    args: tuple[str, ...],
) -> str:
    """Execute a single command on an active session."""
    match command:
        case Command.GOTO:
            if not args:
                raise SystemExit("Usage: browsectl goto <url>")
            info = await gateway.navigate(session, args[0])
            return f"{info.title}\n{info.url}"

        case Command.SCREENSHOT:
            shot = await gateway.screenshot(session)
            out_path = Path(args[0]) if args else SCREENSHOT_PATH
            out_path.write_bytes(shot.data)
            return f"Saved to {out_path} ({len(shot.data)} bytes)"

        case Command.CLICK:
            if not args:
                raise SystemExit("Usage: browsectl click <selector>")
            await gateway.click(session, args[0])
            return f"Clicked: {args[0]}"

        case Command.TYPE:
            if len(args) < 2:
                raise SystemExit("Usage: browsectl type <selector> <text>")
            await gateway.type_text(session, args[0], args[1])
            return f"Typed into: {args[0]}"

        case Command.HTML:
            if not args:
                raise SystemExit("Usage: browsectl html <selector>")
            return await gateway.extract_html(session, args[0])

        case Command.EVAL:
            if not args:
                raise SystemExit("Usage: browsectl eval <expression>")
            result = await gateway.eval_js(session, args[0])
            return result.value

        case Command.INFO:
            info = await gateway.page_info(session)
            return f"{info.title}\n{info.url}"

        case Command.TABS:
            tabs = await gateway.list_tabs(session)
            lines = tuple(f"{t.id}  {t.title}  {t.url}" for t in tabs)
            return "\n".join(lines) if lines else "(no tabs)"

        case Command.NEWTAB:
            url = args[0] if args else "about:blank"
            tab = await gateway.new_tab(session, url)
            return f"Opened tab: {tab.id}  {tab.url}"

        case Command.SWITCHTAB:
            if not args:
                raise SystemExit("Usage: browsectl switchtab <tab-id>")
            await gateway.switch_tab(session, args[0])
            info = await gateway.page_info(session)
            return f"Switched to: {info.title}\n{info.url}"

        case Command.CONNECT:
            return ""
