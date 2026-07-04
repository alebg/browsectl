"""Tests for CDP operations."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from browsectl.adapters.cdp import (
    CdpError,
    CdpSession,
    CdpTimeoutError,
    click,
    eval_js,
    extract_html,
    navigate,
    screenshot,
    scroll,
    type_text,
    wait_for,
)
from browsectl.models import BrowserEndpoint, EvalResult, PageInfo, Screenshot


def _make_session() -> CdpSession:
    ws = AsyncMock()
    ep = BrowserEndpoint(host="localhost", port=9222)
    return CdpSession(ws=ws, target_id="t1", endpoint=ep)


def _mock_send(results: list[dict[str, object]]):  # noqa: ANN201
    return patch(
        "browsectl.adapters.cdp.send_command",
        AsyncMock(side_effect=results),
    )


class TestNavigate:
    @pytest.mark.asyncio
    async def test_returns_page_info(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps({"method": "Page.loadEventFired", "params": {}})
        )
        with _mock_send([
            {},
            {"frameId": "f1"},
            {"result": {"value": '{"url":"http://x.com","title":"X"}'}},
        ]):
            result = await navigate(session, "http://x.com")
        assert result == PageInfo(url="http://x.com", title="X")

    @pytest.mark.asyncio
    async def test_timeout_on_load_event(self) -> None:
        session = _make_session()

        async def _hang() -> str:
            await asyncio.sleep(999)
            return ""

        session.ws.recv = AsyncMock(side_effect=_hang)
        with (
            _mock_send([{}, {"frameId": "f1"}]),
            patch("browsectl.adapters.cdp.CDP_TIMEOUT", 0.05),
            pytest.raises(CdpTimeoutError, match="Page load timed out"),
        ):
            await navigate(session, "http://slow.com")


class TestScreenshot:
    @pytest.mark.asyncio
    async def test_decodes_base64(self) -> None:
        session = _make_session()
        raw = b"\x89PNG"
        with _mock_send([{"data": base64.b64encode(raw).decode()}]):
            result = await screenshot(session)
        assert result == Screenshot(data=raw, format="png")

    @pytest.mark.asyncio
    async def test_raises_on_missing_data(self) -> None:
        session = _make_session()
        with _mock_send([{}]):
            with pytest.raises(CdpError, match="no image data"):
                await screenshot(session)


class TestClick:
    @pytest.mark.asyncio
    async def test_dispatches_events(self) -> None:
        session = _make_session()
        with _mock_send([
            {"result": {"value": '{"x":50,"y":75}'}},
            {},
            {},
        ]):
            await click(session, "#btn")

    @pytest.mark.asyncio
    async def test_raises_on_missing(self) -> None:
        session = _make_session()
        exc_details = {"exception": {"description": "Element not found"}}
        with _mock_send([{
            "result": {"type": "object"},
            "exceptionDetails": exc_details,
        }]):
            with pytest.raises(CdpError):
                await click(session, "#x")


class TestTypeText:
    @pytest.mark.asyncio
    async def test_types_chars(self) -> None:
        session = _make_session()
        with _mock_send([{"result": {"type": "undefined"}}, {}, {}, {}, {}]):
            await type_text(session, "#in", "hi")

    @pytest.mark.asyncio
    async def test_raises_on_focus_fail(self) -> None:
        session = _make_session()
        with _mock_send([{
            "result": {"type": "object"},
            "exceptionDetails": {"exception": {"description": "not found"}},
        }]):
            with pytest.raises(CdpError, match="Focus failed"):
                await type_text(session, "#x", "a")


class TestExtractHtml:
    @pytest.mark.asyncio
    async def test_returns_html(self) -> None:
        session = _make_session()
        with _mock_send([{"result": {"value": "<b>hi</b>"}}]):
            assert await extract_html(session, "#c") == "<b>hi</b>"

    @pytest.mark.asyncio
    async def test_raises_on_missing(self) -> None:
        session = _make_session()
        with _mock_send([{"result": {}, "exceptionDetails": {}}]):
            with pytest.raises(CdpError):
                await extract_html(session, "#x")

    @pytest.mark.asyncio
    async def test_raises_on_unexpected_structure(self) -> None:
        session = _make_session()
        with _mock_send([{"result": {"value": 123}}]):
            with pytest.raises(CdpError, match="no string value"):
                await extract_html(session, "#c")


class TestEvalJs:
    @pytest.mark.asyncio
    async def test_returns_value(self) -> None:
        session = _make_session()
        with _mock_send([{"result": {"value": 42}}]):
            assert await eval_js(session, "21+21") == EvalResult(value="42")

    @pytest.mark.asyncio
    async def test_raises_on_error(self) -> None:
        session = _make_session()
        with _mock_send([{
            "result": {},
            "exceptionDetails": {"exception": {"description": "ReferenceError"}},
        }]):
            with pytest.raises(CdpError, match="ReferenceError"):
                await eval_js(session, "x")

    @pytest.mark.asyncio
    async def test_raises_on_unexpected_structure(self) -> None:
        session = _make_session()
        with _mock_send([{"not_result": "bad"}]):
            with pytest.raises(CdpError, match="unexpected response"):
                await eval_js(session, "1+1")


class TestScroll:
    @pytest.mark.asyncio
    async def test_scrolls_by_pixels(self) -> None:
        session = _make_session()
        with _mock_send([{}]) as mock:
            await scroll(session, 500)
        call_args = mock.call_args_list[0]
        assert call_args[0][1] == "Runtime.evaluate"
        assert "500" in str(call_args[0][2])

    @pytest.mark.asyncio
    async def test_scrolls_negative(self) -> None:
        session = _make_session()
        with _mock_send([{}]) as mock:
            await scroll(session, -200)
        call_args = mock.call_args_list[0]
        assert "-200" in str(call_args[0][2])


class TestWaitFor:
    @pytest.mark.asyncio
    async def test_returns_when_element_found(self) -> None:
        session = _make_session()
        with _mock_send([{"result": {"value": True}}]):
            await wait_for(session, "#target", timeout=5.0)

    @pytest.mark.asyncio
    async def test_polls_until_found(self) -> None:
        session = _make_session()
        with _mock_send([
            {"result": {"value": False}},
            {"result": {"value": False}},
            {"result": {"value": True}},
        ]):
            await wait_for(session, "#target", timeout=5.0)

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self) -> None:
        session = _make_session()
        with (
            _mock_send([{"result": {"value": False}}] * 100),
            pytest.raises(CdpTimeoutError, match="not found after"),
        ):
            await wait_for(session, "#missing", timeout=0.15)
