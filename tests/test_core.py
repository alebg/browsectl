"""Tests for core command dispatch."""

import json
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
        scroll=AsyncMock(),
        wait_for=AsyncMock(),
    )


class TestDispatchConnect:
    @pytest.mark.asyncio
    async def test_saves_session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        result = await dispatch(gw, Command.CONNECT, ("localhost", "9222"))
        assert "9222" in result
        session_file = tmp_path / "default.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["host"] == "localhost"
        assert data["port"] == 9222


class TestDispatchCommands:
    @pytest.fixture(autouse=True)
    def _session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        session_file = tmp_path / "default.json"
        session_file.write_text(json.dumps({"host": "localhost", "port": 9222}))
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)

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

    @pytest.mark.asyncio
    async def test_scroll(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.SCROLL, ("500",))
        assert "500" in result
        gw.scroll.assert_called_once_with("session", 500)

    @pytest.mark.asyncio
    async def test_wait(self) -> None:
        gw = _make_gateway()
        result = await dispatch(gw, Command.WAIT, ("#target", "5"))
        assert "#target" in result
        gw.wait_for.assert_called_once_with("session", "#target", 5.0)

    @pytest.mark.asyncio
    async def test_switchtab_persists_target(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        session_file = tmp_path / "default.json"
        session_file.write_text(json.dumps({"host": "localhost", "port": 9222}))
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        await dispatch(gw, Command.SWITCHTAB, ("t2",))
        data = json.loads(session_file.read_text())
        assert data["target_id"] == "t2"


class TestNamedSessions:
    @pytest.mark.asyncio
    async def test_uses_named_session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        await dispatch(
            gw, Command.CONNECT, ("localhost", "9222"), session_name="linkedin"
        )
        assert (tmp_path / "linkedin.json").exists()
        assert not (tmp_path / "default.json").exists()

    @pytest.mark.asyncio
    async def test_loads_named_session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        from browsectl.models import BrowserEndpoint
        session_file = tmp_path / "work.json"
        session_file.write_text(
            json.dumps({"host": "remote", "port": 1234, "target_id": "t5"})
        )
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        await dispatch(gw, Command.INFO, (), session_name="work")
        gw.connect.assert_called_once_with(
            BrowserEndpoint(host="remote", port=1234), "t5"
        )

    @pytest.mark.asyncio
    async def test_connect_passes_target_id(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        session_file = tmp_path / "default.json"
        session_file.write_text(
            json.dumps({"host": "localhost", "port": 9222, "target_id": "t3"})
        )
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        await dispatch(gw, Command.INFO, ())
        from browsectl.models import BrowserEndpoint
        gw.connect.assert_called_once_with(
            BrowserEndpoint(host="localhost", port=9222), "t3"
        )
