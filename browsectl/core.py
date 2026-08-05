"""Command orchestration -- browser-agnostic business logic."""

import asyncio
import fcntl
import json
import logging
import os
import shutil
import signal
import socket
import time
from pathlib import Path

from browsectl.gateway import BrowserGateway
from browsectl.models import PROFILES_DIR, SESSIONS_DIR, BrowserEndpoint, Command

logger = logging.getLogger(__name__)
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


def _session_status(pid: object) -> tuple[bool, str]:
    """Check if a PID is alive and return (alive, status_label)."""
    if not isinstance(pid, int):
        return False, "external"
    try:
        os.kill(pid, 0)
        return True, "running"
    except ProcessLookupError:
        return False, "dead"
    except PermissionError:
        return True, "running"


def list_sessions(*, prune: bool = False) -> str:
    """List all saved sessions with their status. Optionally prune dead ones."""
    if not SESSIONS_DIR.exists():
        return "(no sessions)"
    files = sorted(SESSIONS_DIR.glob("*.json"))
    if not files:
        return "(no sessions)"
    lines: list[str] = []
    pruned: list[str] = []
    for f in files:
        name = f.stem
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            if prune:
                f.unlink()
                pruned.append(name)
            else:
                lines.append(f"{name}  (corrupt session file)")
            continue
        host = data.get("host", "?")
        port = data.get("port", "?")
        pid = data.get("pid")
        alive, status = _session_status(pid)
        if prune and not alive:
            f.unlink()
            pruned.append(name)
        else:
            lines.append(f"{name}  {host}:{port}  pid={pid}  {status}")
    parts: list[str] = []
    if lines:
        parts.append("\n".join(lines))
    if pruned:
        parts.append(f"Pruned {len(pruned)} stale session(s): {', '.join(pruned)}")
    if not parts:
        return "(no sessions)"
    return "\n".join(parts)


def stop_all_sessions() -> str:
    """Stop all sessions, killing any running processes."""
    if not SESSIONS_DIR.exists():
        return "(no sessions to stop)"
    files = sorted(SESSIONS_DIR.glob("*.json"))
    if not files:
        return "(no sessions to stop)"
    results: list[str] = []
    for f in files:
        name = f.stem
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            f.unlink()
            results.append(f"{name}: removed (corrupt file)")
            continue
        pid = data.get("pid")
        if isinstance(pid, int):
            try:
                os.kill(pid, signal.SIGTERM)
                results.append(f"{name}: stopped (pid {pid})")
            except ProcessLookupError:
                results.append(f"{name}: removed (process already dead)")
        else:
            results.append(f"{name}: removed (no associated process)")
        f.unlink()
    return "\n".join(results)


def _active_session_names() -> frozenset[str]:
    """Return the set of session names that have a session file."""
    if not SESSIONS_DIR.exists():
        return frozenset()
    return frozenset(f.stem for f in SESSIONS_DIR.glob("*.json"))


def list_profiles(*, prune: bool = False) -> str:
    """List all profile directories. Optionally prune orphaned ones."""
    if not PROFILES_DIR.exists():
        return "(no profiles)"
    dirs = sorted(
        d for d in PROFILES_DIR.iterdir() if d.is_dir()
    )
    if not dirs:
        return "(no profiles)"
    active = _active_session_names()
    lines: list[str] = []
    pruned: list[str] = []
    for d in dirs:
        name = d.name
        has_session = name in active
        status = "active" if has_session else "orphaned"
        if prune and not has_session:
            shutil.rmtree(d)
            pruned.append(name)
        else:
            lines.append(f"{name}  {status}")
    parts: list[str] = []
    if lines:
        parts.append("\n".join(lines))
    if pruned:
        parts.append(
            f"Pruned {len(pruned)} orphaned profile(s): "
            f"{', '.join(pruned)}"
        )
    if not parts:
        return "(no profiles)"
    return "\n".join(parts)


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
    timeout: float = LAUNCH_TIMEOUT,
) -> None:
    """Poll until Chrome's CDP endpoint is reachable."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            session = await gateway.connect(endpoint, None)
            await gateway.disconnect(session)
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(LAUNCH_POLL_INTERVAL)
    msg = f"Chrome did not become ready within {timeout}s"
    if last_error is not None:
        msg += f": {last_error}"
    raise SystemExit(msg)


def _parse_launch_args(
    args: tuple[str, ...],
) -> tuple[int | None, str, float, bool]:
    """Parse launch command args. Returns (port_or_none, host, timeout, foreground)."""
    remaining = list(args)
    host = DEFAULT_HOST
    timeout = LAUNCH_TIMEOUT
    foreground = False
    port_str: str | None = None

    i = 0
    while i < len(remaining):
        if remaining[i] == "--host":
            if i + 1 >= len(remaining):
                raise SystemExit("--host requires a value")
            host = remaining[i + 1]
            i += 2
        elif remaining[i] == "--timeout":
            if i + 1 >= len(remaining):
                raise SystemExit("--timeout requires a value")
            try:
                timeout = float(remaining[i + 1])
            except ValueError:
                raise SystemExit(f"Invalid timeout: {remaining[i + 1]}")
            i += 2
        elif remaining[i] == "--foreground":
            foreground = True
            i += 1
        else:
            if port_str is None:
                port_str = remaining[i]
            i += 1

    if port_str is None:
        return None, host, timeout, foreground
    try:
        port = int(port_str)
    except ValueError:
        raise SystemExit(f"Invalid port: {port_str}")
    return port, host, timeout, foreground


async def dispatch[S](
    gateway: BrowserGateway[S],
    command: Command,
    args: tuple[str, ...],
    session_name: str,
) -> str:
    """Dispatch a CLI command through the gateway. Returns output text."""
    if command == Command.LAUNCH:
        requested_port, host, timeout, foreground = _parse_launch_args(args)
        if requested_port is not None:
            _check_port_free(host, requested_port)
            port = requested_port
        else:
            port = _find_free_port(host)
        process = gateway.launch_browser(session_name, port, foreground)
        endpoint = BrowserEndpoint(host=host, port=port)
        try:
            await _wait_for_cdp(gateway, endpoint, timeout)
        except SystemExit:
            process.terminate()
            raise
        save_session(endpoint, name=session_name, pid=process.pid)
        mode = "foreground" if foreground else "background"
        return f"Launched Chrome on {host}:{port} (pid {process.pid}, {mode})"

    if command == Command.STOP:
        return stop_session(session_name)

    if command == Command.SESSIONS:
        prune = "--prune" in args
        return list_sessions(prune=prune)

    if command == Command.STOP_ALL:
        return stop_all_sessions()

    if command == Command.PROFILES:
        prune = "--prune" in args
        return list_profiles(prune=prune)

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

        case (
            Command.CONNECT
            | Command.LAUNCH
            | Command.STOP
            | Command.SESSIONS
            | Command.STOP_ALL
            | Command.PROFILES
        ):
            return ""
