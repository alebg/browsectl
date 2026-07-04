"""Tests for core command dispatch."""

from unittest.mock import AsyncMock

import pytest

from browsectl.core import dispatch
from browsectl.gateway import BrowserGateway
from browsectl.models import (
    Command,
    EvalResult,
    PageInfo,
    Screenshot,
    Tab,
)


def _make_gateway() -> BrowserGateway[str]:
    return BrowserGateway(
        connect=AsyncMock(return_value="session"),
        disconnect=AsyncMock(),
        navigate=AsyncMock(return_value=PageInfo(url="http://x.com", title="X")),
        screenshot=AsyncMock(return_value=Screenshot(data=b"png", format="png")),
        click=AsyncMock(),
        type_text=AsyncMock(),
        extract_html=AsyncMock(return_value="<b>hi</b>"),
        eval_js=AsyncMock(return_value=EvalResult(value="42")),
        page_info=AsyncMock(return_value=PageInfo(url="http://x.com", title="X")),
        list_tabs=AsyncMock(return_value=(
            Tab(id="t1", title="Tab1", url="http://a.com"),
        )),
        new_tab=AsyncMock(return_value=Tab(id="t2", title="", url="about:blank")),
        switch_tab=AsyncMock(),
    )


class TestDispatchConnect:
    @pytest.mark.asyncio
    async def test_saves_session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSION_FILE", tmp_path / "s.json")
        monkeypatch.setattr("browsectl.core.SESSION_DIR", tmp_path)
        gw = _make_gateway()
        result = await dispatch(gw, Command.CONNECT, ("localhost", "9222"))
        assert "9222" in result


class TestDispatchCommands:
    @pytest.fixture(autouse=True)
    def _session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import json
        session_file = tmp_path / "s.json"
        session_file.write_text(json.dumps({"host": "localhost", "port": 9222}))
        monkeypatch.setattr("browsectl.core.SESSION_FILE", session_file)

    @pytest.mark.asyncio
    async def test_goto(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.GOTO, ("http://x.com",))
        assert "X" in result
        gw.navigate.assert_called_once()

    @pytest.mark.asyncio
    async def test_screenshot(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        gw = _make_gateway()
        out = tmp_path / "shot.png"
        result = await dispatch(gw, Command.SCREENSHOT, (str(out),))
        assert out.exists()
        assert "3 bytes" in result

    @pytest.mark.asyncio
    async def test_click(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.CLICK, ("#btn",))
        assert "#btn" in result

    @pytest.mark.asyncio
    async def test_type(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.TYPE, ("#in", "hello"))
        assert "#in" in result

    @pytest.mark.asyncio
    async def test_html(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.HTML, ("#c",))
        assert result == "<b>hi</b>"

    @pytest.mark.asyncio
    async def test_eval(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.EVAL, ("21+21",))
        assert result == "42"

    @pytest.mark.asyncio
    async def test_info(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.INFO, ())
        assert "X" in result
        assert "http://x.com" in result

    @pytest.mark.asyncio
    async def test_tabs(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.TABS, ())
        assert "Tab1" in result
