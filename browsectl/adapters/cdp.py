"""Chrome DevTools Protocol adapter."""

import base64
import json
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


class CdpError(Exception):
    """Raised when a CDP command returns an error."""


type TSendCommand = Callable[
    [CdpSession, str, dict[str, object] | None], Awaitable[dict[str, object]]
]

send_command: TSendCommand = _send_command


async def connect(endpoint: BrowserEndpoint) -> CdpSession:
    """Connect to the first available CDP target."""
    import urllib.request

    list_url = f"http://{endpoint.host}:{endpoint.port}/json"
    with urllib.request.urlopen(list_url) as resp:
        targets = json.loads(resp.read().decode())

    page_targets = [t for t in targets if t.get("type") == "page"]
    if not page_targets:
        raise CdpError("No page targets found")

    target = page_targets[0]
    ws_url = target["webSocketDebuggerUrl"]
    target_id = target["id"]

    ws = await websockets.asyncio.client.connect(ws_url)
    return CdpSession(ws=ws, target_id=target_id, endpoint=endpoint)


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
    raw_value = result.get("result", {})
    if isinstance(raw_value, dict):
        value_str = raw_value.get("value", "{}")
    else:
        value_str = "{}"
    if not isinstance(value_str, str):
        value_str = "{}"
    parsed = json.loads(value_str)
    return PageInfo(
        url=parsed.get("url", ""),
        title=parsed.get("title", ""),
    )


async def navigate(session: CdpSession, url: str) -> PageInfo:
    """Navigate to a URL and wait for the page to load."""
    await send_command(session, "Page.enable", None)
    await send_command(session, "Page.navigate", {"url": url})

    # Wait for Page.loadEventFired
    while True:
        raw = await session.ws.recv()
        msg = json.loads(raw)
        if isinstance(msg, dict) and msg.get("method") == "Page.loadEventFired":
            break

    return await page_info(session)


async def screenshot(session: CdpSession) -> Screenshot:
    """Capture a full-page screenshot as PNG."""
    result = await send_command(
        session,
        "Page.captureScreenshot",
        {"format": "png"},
    )
    data_str = result.get("data", "")
    if not isinstance(data_str, str):
        data_str = ""
    return Screenshot(data=base64.b64decode(data_str), format="png")


async def click(session: CdpSession, selector: str) -> None:
    """Click an element identified by CSS selector."""
    js = f"""
    (() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) throw new Error("Element not found: " + {json.dumps(selector)});
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

    if isinstance(raw_result, dict):
        value_str = raw_result.get("value", "{}")
    else:
        value_str = "{}"
    if not isinstance(value_str, str):
        value_str = "{}"
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
    raw_result = result.get("result", {})
    if isinstance(raw_result, dict):
        value = raw_result.get("value", "")
        if isinstance(value, str):
            return value
    return ""


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
    raw_result = result.get("result", {})
    if isinstance(raw_result, dict):
        value = raw_result.get("value", "")
        return EvalResult(value=str(value))
    return EvalResult(value="")


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
    import urllib.request

    ep = session.endpoint
    list_url = f"http://{ep.host}:{ep.port}/json"
    with urllib.request.urlopen(list_url) as resp:
        targets = json.loads(resp.read().decode())

    target = next(
        (t for t in targets if t.get("id") == target_id),
        None,
    )
    if target is None:
        raise CdpError(f"Tab not found: {target_id}")

    await session.ws.close()
    ws_url = target["webSocketDebuggerUrl"]
    session.ws = await websockets.asyncio.client.connect(ws_url)
    session.target_id = target_id
