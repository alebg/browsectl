"""Tests for the CDP adapter."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from browsectl.adapters.cdp import (
    CdpError,
    CdpSession,
    connect,
    disconnect,
    list_tabs,
    page_info,
    send_command,
)
from browsectl.models import BrowserEndpoint, PageInfo, Tab


def _make_session() -> CdpSession:
    ws = AsyncMock()
    ep = BrowserEndpoint(host="localhost", port=9222)
    return CdpSession(ws=ws, target_id="target-1", endpoint=ep)


class TestCdpSession:
    def test_next_id_increments(self) -> None:
        session = _make_session()
        assert session.next_id() == 1
        assert session.next_id() == 2
        assert session.next_id() == 3


class TestSendCommand:
    @pytest.mark.asyncio
    async def test_sends_and_receives(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps({"id": 1, "result": {"data": "ok"}})
        )

        result = await send_command(session, "Page.navigate", {"url": "http://x.com"})

        session.ws.send.assert_called_once()
        sent = json.loads(session.ws.send.call_args[0][0])
        assert sent["method"] == "Page.navigate"
        assert sent["params"] == {"url": "http://x.com"}
        assert sent["id"] == 1
        assert result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_raises_on_error(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps(
                {"id": 1, "error": {"message": "something broke"}}
            )
        )

        with pytest.raises(CdpError, match="something broke"):
            await send_command(session, "Bad.method")

    @pytest.mark.asyncio
    async def test_skips_events(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"method": "Network.requestWillBeSent", "params": {}}),
                json.dumps({"id": 1, "result": {"done": True}}),
            ]
        )

        result = await send_command(session, "Page.enable")
        assert result == {"done": True}

    @pytest.mark.asyncio
    async def test_no_params(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps({"id": 1, "result": {}})
        )

        await send_command(session, "Page.enable")

        sent = json.loads(session.ws.send.call_args[0][0])
        assert "params" not in sent


class TestConnect:
    @pytest.mark.asyncio
    async def test_connects_to_first_page_target(self) -> None:
        targets = [
            {
                "type": "page",
                "id": "ABC123",
                "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/ABC123",
            },
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(targets).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with (
            patch(
                "urllib.request.urlopen", return_value=mock_resp
            ),
            patch(
                "websockets.asyncio.client.connect", new_callable=AsyncMock
            ) as mock_ws_connect,
        ):
            mock_ws_connect.return_value = AsyncMock()
            endpoint = BrowserEndpoint(host="localhost", port=9222)
            session = await connect(endpoint)

            assert session.target_id == "ABC123"
            mock_ws_connect.assert_called_once_with(
                "ws://localhost:9222/devtools/page/ABC123"
            )

    @pytest.mark.asyncio
    async def test_raises_when_no_page_targets(self) -> None:
        targets = [{"type": "service_worker", "id": "sw1"}]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(targets).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            endpoint = BrowserEndpoint(host="localhost", port=9222)
            with pytest.raises(CdpError, match="No page targets"):
                await connect(endpoint)


class TestListTabs:
    @pytest.mark.asyncio
    async def test_returns_page_targets(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps({
                "id": 1,
                "result": {
                    "targetInfos": [
                        {
                            "targetId": "t1",
                            "type": "page",
                            "title": "Google",
                            "url": "https://google.com",
                        },
                        {
                            "targetId": "t2",
                            "type": "service_worker",
                            "title": "",
                            "url": "sw.js",
                        },
                        {
                            "targetId": "t3",
                            "type": "page",
                            "title": "GitHub",
                            "url": "https://github.com",
                        },
                    ]
                },
            })
        )

        tabs = await list_tabs(session)

        assert tabs == (
            Tab(id="t1", title="Google", url="https://google.com"),
            Tab(id="t3", title="GitHub", url="https://github.com"),
        )

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pages(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps({
                "id": 1,
                "result": {"targetInfos": []},
            })
        )

        tabs = await list_tabs(session)
        assert tabs == ()


class TestPageInfo:
    @pytest.mark.asyncio
    async def test_returns_url_and_title(self) -> None:
        session = _make_session()
        session.ws.recv = AsyncMock(
            return_value=json.dumps({
                "id": 1,
                "result": {
                    "result": {
                        "type": "string",
                        "value": json.dumps({
                            "url": "https://example.com/page",
                            "title": "Example Page",
                        }),
                    }
                },
            })
        )

        info = await page_info(session)
        assert info == PageInfo(url="https://example.com/page", title="Example Page")


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_closes_websocket(self) -> None:
        session = _make_session()
        await disconnect(session)
        session.ws.close.assert_called_once()
