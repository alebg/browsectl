"""Command orchestration -- browser-agnostic business logic."""

import asyncio
import fcntl
import json
import logging
import os
import signal
import socket
import time
from pathlib import Path

from browsectl.gateway import BrowserGateway
from browsectl.models import BrowserEndpoint, Command

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path.home() / ".browsectl" / "sessions"
SCREENSHOT_PATH = Path("screenshot.png")
DEFAULT_HOST: str = "localhost"
LAUNCH_TIMEOUT: float = 15.0
LAUNCH_POLL_INTERVAL: float = 0.3


def _session_file(name: str) -> Path:
    return SESSIONS_DIR / f"{name}.json"


def load_session(name: str) -> tuple[BrowserEndpoint, str | None]:
    """Load the saved browser endpoint and target from the session file."""
    path = _session_file(name)
    if not path.exists():
        raise SystemExit(
            f"No active session '{name}'. "
            f"Run: browsectl -s {name} connect <host> <port>"
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
    *,
    name: str,
    pid: int | None = None,
) -> None:
    """Save the browser endpoint and optional target to the session file."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {"host": endpoint.host, "port": endpoint.port}
    if target_id is not None:
        data["target_id"] = target_id
    if pid is not None:
        data["pid"] = pid
    path = _session_file(name)
    with path.open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(data))


def stop_session(name: str) -> str:
    """Stop a launched Chrome session by killing its process."""
    path = _session_file(name)
    if not path.exists():
        raise SystemExit(f"No session '{name}' found.")
    data = json.loads(path.read_text())
    pid = data.get("pid")
    if not isinstance(pid, int):
        path.unlink()
        return f"Session '{name}' removed (no associated process)."
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    path.unlink()
    return f"Stopped session '{name}' (pid {pid})."


def list_sessions() -> str:
    """List all saved sessions with their status."""
    if not SESSIONS_DIR.exists():
        return "(no sessions)"
    files = sorted(SESSIONS_DIR.glob("*.json"))
    if not files:
        return "(no sessions)"
    lines: list[str] = []
    for f in files:
        name = f.stem
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            lines.append(f"{name}  (corrupt session file)")
            continue
        host = data.get("host", "?")
        port = data.get("port", "?")
        pid = data.get("pid")
        alive = False
        if isinstance(pid, int):
            try:
                os.kill(pid, 0)
                alive = True
            except ProcessLookupError:
                pass
            except PermissionError:
                alive = True
        status = "running" if alive else "dead" if isinstance(pid, int) else "external"
        lines.append(f"{name}  {host}:{port}  pid={pid}  {status}")
    return "\n".join(lines)


def _find_free_port(host: str) -> int:
    """Ask the OS for a free ephemeral port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        addr = sock.getsockname()
        port: int = int(addr[1])
        return port
    finally:
        sock.close()


def _check_port_free(host: str, port: int) -> None:
    """Fail fast if the port is already in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            raise SystemExit(
                f"Port {port} is already in use on {host}.\n"
                f"Choose a different port or stop the existing process."
            )
    finally:
        sock.close()


async def _wait_for_cdp[S](
    gateway: BrowserGateway[S],
    endpoint: BrowserEndpoint,
) -> None:
    """Poll until Chrome's CDP endpoint is reachable."""
    deadline = time.monotonic() + LAUNCH_TIMEOUT
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            session = await gateway.connect(endpoint, None)
            await gateway.disconnect(session)
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(LAUNCH_POLL_INTERVAL)
    msg = f"Chrome did not become ready within {LAUNCH_TIMEOUT}s"
    if last_error is not None:
        msg += f": {last_error}"
    raise SystemExit(msg)


def _parse_launch_args(
    args: tuple[str, ...],
) -> tuple[int | None, str]:
    """Parse launch command args. Returns (port_or_none, host)."""
    remaining = list(args)
    host = DEFAULT_HOST
    port_str: str | None = None

    i = 0
    while i < len(remaining):
        if remaining[i] == "--host":
            if i + 1 >= len(remaining):
                raise SystemExit("--host requires a value")
            host = remaining[i + 1]
            i += 2
        else:
            if port_str is None:
                port_str = remaining[i]
            i += 1

    if port_str is None:
        return None, host
    try:
        port = int(port_str)
    except ValueError:
        raise SystemExit(f"Invalid port: {port_str}")
    return port, host


async def dispatch[S](
    gateway: BrowserGateway[S],
    command: Command,
    args: tuple[str, ...],
    session_name: str,
) -> str:
    """Dispatch a CLI command through the gateway. Returns output text."""
    if command == Command.LAUNCH:
        requested_port, host = _parse_launch_args(args)
        if requested_port is not None:
            _check_port_free(host, requested_port)
            port = requested_port
        else:
            port = _find_free_port(host)
        process = gateway.launch_browser(session_name, port)
        endpoint = BrowserEndpoint(host=host, port=port)
        try:
            await _wait_for_cdp(gateway, endpoint)
        except SystemExit:
            process.terminate()
            raise
        save_session(endpoint, name=session_name, pid=process.pid)
        return f"Launched Chrome on {host}:{port} (pid {process.pid})"

    if command == Command.STOP:
        return stop_session(session_name)

    if command == Command.SESSIONS:
        return list_sessions()

    if command == Command.CONNECT:
        missing: list[str] = []
        if not args:
            missing.append("host")
        if len(args) < 2:
            missing.append("port")
        if missing:
            raise SystemExit(
                f"Missing required arguments: {', '.join(missing)}\n"
                f"Usage: browsectl -s <session> connect <host> <port>"
            )
        host = args[0]
        port = int(args[1])
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

        case Command.CLEAR_COOKIES:
            await gateway.clear_cookies(session)
            return "Cookies cleared"

        case Command.CONNECT | Command.LAUNCH | Command.STOP | Command.SESSIONS:
            return ""
