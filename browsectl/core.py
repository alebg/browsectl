"""Command orchestration -- browser-agnostic business logic."""

import fcntl
import json
import logging
from pathlib import Path

from browsectl.gateway import BrowserGateway
from browsectl.models import BrowserEndpoint, Command

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path.home() / ".browsectl" / "sessions"
SCREENSHOT_PATH = Path("screenshot.png")


def _session_file(name: str) -> Path:
    return SESSIONS_DIR / f"{name}.json"


def load_session(name: str = "default") -> tuple[BrowserEndpoint, str | None]:
    """Load the saved browser endpoint and target from the session file."""
    path = _session_file(name)
    if not path.exists():
        raise SystemExit(
            "No active session. Run: browsectl connect <host> <port>"
        )
    data = json.loads(path.read_text())
    target_id = data.get("target_id")
    return (
        BrowserEndpoint(host=data["host"], port=data["port"]),
        target_id if isinstance(target_id, str) else None,
    )


def save_session(
    endpoint: BrowserEndpoint,
    target_id: str | None = None,
    name: str = "default",
) -> None:
    """Save the browser endpoint and optional target to the session file."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {"host": endpoint.host, "port": endpoint.port}
    if target_id is not None:
        data["target_id"] = target_id
    path = _session_file(name)
    with path.open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(data))


async def dispatch[S](
    gateway: BrowserGateway[S],
    command: Command,
    args: tuple[str, ...],
    session_name: str = "default",
) -> str:
    """Dispatch a CLI command through the gateway. Returns output text."""
    if command == Command.CONNECT:
        host = args[0] if args else "localhost"
        port = int(args[1]) if len(args) > 1 else 9222
        endpoint = BrowserEndpoint(host=host, port=port)
        session = await gateway.connect(endpoint, None)
        await gateway.disconnect(session)
        save_session(endpoint, name=session_name)
        return f"Connected to {host}:{port}"

    endpoint, target_id = load_session(session_name)
    session = await gateway.connect(endpoint, target_id)
    try:
        result = await _run_command(gateway, session, command, args)
        if command == Command.SWITCHTAB and args:
            save_session(endpoint, target_id=args[0], name=session_name)
        return result
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

        case Command.SCROLL:
            if not args:
                raise SystemExit("Usage: browsectl scroll <pixels>")
            await gateway.scroll(session, int(args[0]))
            return f"Scrolled {args[0]}px"

        case Command.WAIT:
            if not args:
                raise SystemExit("Usage: browsectl wait <selector> [timeout]")
            timeout = float(args[1]) if len(args) > 1 else 30.0
            await gateway.wait_for(session, args[0], timeout)
            return f"Found: {args[0]}"

        case Command.CONNECT:
            return ""
