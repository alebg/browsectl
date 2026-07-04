"""Chrome DevTools Protocol adapter."""

import asyncio
import base64
import json
import urllib.request
from collections.abc import Awaitable, Callable

import attrs
import websockets.asyncio.client

from browsectl.models import (
    BrowserEndpoint,
    EvalResult,
    PageInfo,
    Screenshot,
    Tab,
)

CDP_TIMEOUT: float = 30.0


class CdpError(Exception):
    """Raised when a CDP command returns an error."""


class CdpTimeoutError(CdpError):
    """Raised when a CDP operation exceeds its timeout."""


@attrs.define(slots=True)
class CdpSession:
    """Holds a live websocket connection to a CDP target."""

    ws: websockets.asyncio.client.ClientConnection
    target_id: str
    endpoint: BrowserEndpoint
    _msg_id: int = 0

    def next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id


def _fetch_json(url: str) -> bytes:
    """Blocking HTTP GET — run via asyncio.to_thread."""
    with urllib.request.urlopen(url) as resp:
        return resp.read()  # type: ignore[no-any-return]


async def _send_command(
    session: CdpSession,
    method: str,
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    """Send a CDP command and return the result."""
    msg_id = session.next_id()
    payload: dict[str, object] = {"id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    await session.ws.send(json.dumps(payload))

    async def _recv_response() -> dict[str, object]:
        while True:
            raw = await session.ws.recv()
            response = json.loads(raw)
            if isinstance(response, dict) and response.get("id") == msg_id:
                if "error" in response:
                    error = response["error"]
                    if isinstance(error, dict):
                        msg = error.get("message", str(error))
                    else:
                        msg = str(error)
                    raise CdpError(msg)
                result = response.get("result")
                if isinstance(result, dict):
                    return result
                return {}

    try:
        return await asyncio.wait_for(_recv_response(), timeout=CDP_TIMEOUT)
    except TimeoutError:
        raise CdpTimeoutError(
            f"CDP command {method} timed out after {CDP_TIMEOUT}s"
        )


type TSendCommand = Callable[
    [CdpSession, str, dict[str, object] | None], Awaitable[dict[str, object]]
]

send_command: TSendCommand = _send_command


async def connect(
    endpoint: BrowserEndpoint, target_id: str | None = None
) -> CdpSession:
    """Connect to a CDP target, preferring target_id if it still exists."""
    list_url = f"http://{endpoint.host}:{endpoint.port}/json"
    raw = await asyncio.to_thread(_fetch_json, list_url)
    targets = json.loads(raw.decode())

    page_targets = [t for t in targets if t.get("type") == "page"]
    if not page_targets:
        raise CdpError("No page targets found")

    target = None
    if target_id is not None:
        target = next(
            (t for t in page_targets if t.get("id") == target_id),
            None,
        )
    if target is None:
        target = page_targets[0]

    ws_url: str = target["webSocketDebuggerUrl"]
    tid: str = target["id"]

    ws = await websockets.asyncio.client.connect(ws_url)
    return CdpSession(ws=ws, target_id=tid, endpoint=endpoint)


async def disconnect(session: CdpSession) -> None:
    """Close the websocket connection."""
    await session.ws.close()


async def list_tabs(session: CdpSession) -> tuple[Tab, ...]:
    """List all page targets via the Target domain."""
    result = await send_command(session, "Target.getTargets", None)
    raw_targets = result.get("targetInfos", [])
    if not isinstance(raw_targets, list):
        return ()
    return tuple(
        Tab(
            id=t["targetId"],
            title=t.get("title", ""),
            url=t.get("url", ""),
        )
        for t in raw_targets
        if isinstance(t, dict) and t.get("type") == "page"
    )


async def page_info(session: CdpSession) -> PageInfo:
    """Get the current page's URL and title."""
    result = await send_command(
        session,
        "Runtime.evaluate",
        {"expression": "JSON.stringify({url: location.href, title: document.title})"},
    )
    raw_value = result.get("result")
    if not isinstance(raw_value, dict):
        raise CdpError("page_info: unexpected response structure")
    value_str = raw_value.get("value")
    if not isinstance(value_str, str):
        raise CdpError("page_info: missing result value")
    parsed = json.loads(value_str)
    return PageInfo(
        url=parsed.get("url", ""),
        title=parsed.get("title", ""),
    )


async def navigate(session: CdpSession, url: str) -> PageInfo:
    """Navigate to a URL and wait for the page to load."""
    await send_command(session, "Page.enable", None)
    await send_command(session, "Page.navigate", {"url": url})

    async def _wait_for_load() -> None:
        while True:
            raw = await session.ws.recv()
            msg = json.loads(raw)
            if isinstance(msg, dict) and msg.get("method") == "Page.loadEventFired":
                break

    try:
        await asyncio.wait_for(_wait_for_load(), timeout=CDP_TIMEOUT)
    except TimeoutError:
        raise CdpTimeoutError(f"Page load timed out after {CDP_TIMEOUT}s")

    return await page_info(session)


async def screenshot(session: CdpSession) -> Screenshot:
    """Capture a full-page screenshot as PNG."""
    result = await send_command(
        session,
        "Page.captureScreenshot",
        {"format": "png"},
    )
    data_str = result.get("data")
    if not isinstance(data_str, str) or not data_str:
        raise CdpError("screenshot: no image data in response")
    return Screenshot(data=base64.b64decode(data_str), format="png")


async def click(session: CdpSession, selector: str) -> None:
    """Click an element identified by CSS selector."""
    js = f"""
    (() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) throw new Error("Element not found: " + {json.dumps(selector)});
        el.scrollIntoView({{block: 'center'}});
        const rect = el.getBoundingClientRect();
        return JSON.stringify({{
            x: rect.x + rect.width / 2,
            y: rect.y + rect.height / 2
        }});
    }})()
    """
    result = await send_command(
        session,
        "Runtime.evaluate",
        {"expression": js, "returnByValue": True},
    )
    raw_result = result.get("result", {})
    if isinstance(raw_result, dict) and "exceptionDetails" in result:
        desc = result.get("exceptionDetails", {})
        if isinstance(desc, dict):
            exc = desc.get("exception", {})
            if isinstance(exc, dict):
                raise CdpError(str(exc.get("description", "click failed")))
        raise CdpError("click failed")

    if not isinstance(raw_result, dict):
        raise CdpError("click: unexpected response structure")
    value_str = raw_result.get("value")
    if not isinstance(value_str, str):
        raise CdpError("click: missing coordinate data")
    coords = json.loads(value_str)
    x = float(coords.get("x", 0))
    y = float(coords.get("y", 0))

    for event_type in ("mousePressed", "mouseReleased"):
        await send_command(
            session,
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )


async def type_text(session: CdpSession, selector: str, text: str) -> None:
    """Focus an element and type text into it."""
    focus_js = f"""
    (() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) throw new Error("Element not found: " + {json.dumps(selector)});
        el.focus();
    }})()
    """
    result = await send_command(
        session,
        "Runtime.evaluate",
        {"expression": focus_js},
    )
    if "exceptionDetails" in result:
        raise CdpError(f"Focus failed for selector: {selector}")

    for char in text:
        await send_command(
            session,
            "Input.dispatchKeyEvent",
            {"type": "keyDown", "text": char},
        )
        await send_command(
            session,
            "Input.dispatchKeyEvent",
            {"type": "keyUp"},
        )


async def extract_html(session: CdpSession, selector: str) -> str:
    """Extract the innerHTML of an element by CSS selector."""
    js = f"""
    (() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) throw new Error("Element not found: " + {json.dumps(selector)});
        return el.innerHTML;
    }})()
    """
    result = await send_command(
        session,
        "Runtime.evaluate",
        {"expression": js, "returnByValue": True},
    )
    if "exceptionDetails" in result:
        raise CdpError(f"Element not found: {selector}")
    raw_result = result.get("result")
    if not isinstance(raw_result, dict):
        raise CdpError("extract_html: unexpected response structure")
    value = raw_result.get("value")
    if not isinstance(value, str):
        raise CdpError("extract_html: no string value in result")
    return value


async def eval_js(session: CdpSession, expression: str) -> EvalResult:
    """Evaluate a JS expression and return the result."""
    result = await send_command(
        session,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
    )
    if "exceptionDetails" in result:
        exc_details = result["exceptionDetails"]
        if isinstance(exc_details, dict):
            exc = exc_details.get("exception", {})
            if isinstance(exc, dict):
                raise CdpError(str(exc.get("description", "eval failed")))
        raise CdpError("eval failed")
    raw_result = result.get("result")
    if not isinstance(raw_result, dict):
        raise CdpError("eval_js: unexpected response structure")
    return EvalResult(value=str(raw_result.get("value", "")))


async def new_tab(session: CdpSession, url: str) -> Tab:
    """Create a new tab and return its info."""
    result = await send_command(
        session,
        "Target.createTarget",
        {"url": url},
    )
    target_id = result.get("targetId", "")
    if not isinstance(target_id, str) or not target_id:
        raise CdpError("Failed to create new tab")
    return Tab(id=target_id, title="", url=url)


async def switch_tab(session: CdpSession, target_id: str) -> None:
    """Switch to a different tab by reconnecting to its websocket."""
    ep = session.endpoint
    list_url = f"http://{ep.host}:{ep.port}/json"
    raw = await asyncio.to_thread(_fetch_json, list_url)
    targets = json.loads(raw.decode())

    target = next(
        (t for t in targets if t.get("id") == target_id),
        None,
    )
    if target is None:
        raise CdpError(f"Tab not found: {target_id}")

    ws_url: str = target["webSocketDebuggerUrl"]
    new_ws = await websockets.asyncio.client.connect(ws_url)
    await session.ws.close()
    session.ws = new_ws
    session.target_id = target_id


async def scroll(session: CdpSession, pixels: int) -> None:
    """Scroll the page by N pixels (positive=down, negative=up)."""
    await send_command(
        session,
        "Runtime.evaluate",
        {"expression": f"window.scrollBy(0, {pixels})"},
    )


async def wait_for(session: CdpSession, selector: str, timeout: float = 30.0) -> None:
    """Poll for a CSS selector until it exists or timeout."""
    js = f"document.querySelector({json.dumps(selector)}) !== null"

    async def _poll() -> None:
        while True:
            result = await send_command(
                session,
                "Runtime.evaluate",
                {"expression": js, "returnByValue": True},
            )
            raw = result.get("result")
            if isinstance(raw, dict) and raw.get("value") is True:
                return
            await asyncio.sleep(0.1)

    try:
        await asyncio.wait_for(_poll(), timeout=timeout)
    except TimeoutError:
        raise CdpTimeoutError(
            f"Selector {selector!r} not found after {timeout}s"
        )
