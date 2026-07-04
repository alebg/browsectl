"""Tests for CDP newtab and switchtab operations."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browsectl.adapters.cdp import (
    CdpError,
    CdpSession,
    new_tab,
    switch_tab,
)
from browsectl.models import BrowserEndpoint, Tab


def _make_session() -> CdpSession:
    ws = AsyncMock()
    ep = BrowserEndpoint(host="localhost", port=9222)
    return CdpSession(ws=ws, target_id="t1", endpoint=ep)


def _mock_send(results: list[dict[str, object]]):  # noqa: ANN201
    return patch(
        "browsectl.adapters.cdp.send_command",
        AsyncMock(side_effect=results),
    )


class TestNewTab:
    @pytest.mark.asyncio
    async def test_creates_tab(self) -> None:
        session = _make_session()
        with _mock_send([{"targetId": "t-new"}]):
            tab = await new_tab(session, "https://example.com")
        assert tab == Tab(id="t-new", title="", url="https://example.com")

    @pytest.mark.asyncio
    async def test_raises_on_empty_id(self) -> None:
        session = _make_session()
        with _mock_send([{"targetId": ""}]):
            with pytest.raises(CdpError, match="Failed to create"):
                await new_tab(session, "https://example.com")


class TestSwitchTab:
    @pytest.mark.asyncio
    async def test_reconnects_to_target(self) -> None:
        session = _make_session()
        old_ws = session.ws
        targets = [
            {
                "id": "t2",
                "type": "page",
                "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/t2",
            },
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(targets).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        new_ws = AsyncMock()
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch(
                "websockets.asyncio.client.connect",
                new_callable=AsyncMock,
                return_value=new_ws,
            ),
        ):
            await switch_tab(session, "t2")

        old_ws.close.assert_called_once()
        assert session.target_id == "t2"
        assert session.ws is new_ws

    @pytest.mark.asyncio
    async def test_raises_on_unknown_tab(self) -> None:
        session = _make_session()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([]).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(CdpError, match="Tab not found"):
                await switch_tab(session, "nonexistent")
