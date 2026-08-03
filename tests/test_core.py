"""Tests for core command dispatch."""

import json
import socket
from unittest.mock import AsyncMock, Mock

import pytest

from browsectl.core import (
    _check_port_free,
    _parse_launch_args,
    dispatch,
    list_sessions,
    stop_session,
)
from browsectl.gateway import BrowserGateway
from browsectl.models import (
    Command,
    EvalResult,
    PageInfo,
    Screenshot,
    Tab,
)


def _make_launch_mock() -> Mock:
    mock = Mock()
    mock.return_value.pid = 12345
    return mock


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
        clear_cookies=AsyncMock(),
        launch_browser=_make_launch_mock(),
    )


class TestDispatchConnect:
    @pytest.mark.asyncio
    async def test_saves_session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.CONNECT, ("localhost", "9222"), session_name="test"
        )
        assert "9222" in result
        session_file = tmp_path / "test.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["host"] == "localhost"
        assert data["port"] == 9222

    @pytest.mark.asyncio
    async def test_connect_missing_host_and_port(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        with pytest.raises(SystemExit, match="host"):
            await dispatch(gw, Command.CONNECT, (), session_name="test")

    @pytest.mark.asyncio
    async def test_connect_missing_port(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        with pytest.raises(SystemExit, match="port"):
            await dispatch(
                gw, Command.CONNECT, ("localhost",), session_name="test"
            )


class TestDispatchCommands:
    SESSION_NAME = "test"

    @pytest.fixture(autouse=True)
    def _session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        session_file = tmp_path / f"{self.SESSION_NAME}.json"
        session_file.write_text(json.dumps({"host": "localhost", "port": 9222}))
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)

    @pytest.mark.asyncio
    async def test_goto(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.GOTO, ("http://x.com",), session_name=self.SESSION_NAME
        )
        assert "X" in result
        gw.navigate.assert_called_once()

    @pytest.mark.asyncio
    async def test_screenshot(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        gw = _make_gateway()
        out = tmp_path / "shot.png"
        result = await dispatch(
            gw, Command.SCREENSHOT, (str(out),), session_name=self.SESSION_NAME
        )
        assert out.exists()
        assert "3 bytes" in result

    @pytest.mark.asyncio
    async def test_click(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.CLICK, ("#btn",), session_name=self.SESSION_NAME
        )
        assert "#btn" in result

    @pytest.mark.asyncio
    async def test_type(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.TYPE, ("#in", "hello"), session_name=self.SESSION_NAME
        )
        assert "#in" in result

    @pytest.mark.asyncio
    async def test_html(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.HTML, ("#c",), session_name=self.SESSION_NAME
        )
        assert result == "<b>hi</b>"

    @pytest.mark.asyncio
    async def test_eval(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.EVAL, ("21+21",), session_name=self.SESSION_NAME
        )
        assert result == "42"

    @pytest.mark.asyncio
    async def test_info(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.INFO, (), session_name=self.SESSION_NAME
        )
        assert "X" in result
        assert "http://x.com" in result

    @pytest.mark.asyncio
    async def test_tabs(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.TABS, (), session_name=self.SESSION_NAME
        )
        assert "Tab1" in result

    @pytest.mark.asyncio
    async def test_scroll(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.SCROLL, ("500",), session_name=self.SESSION_NAME
        )
        assert "500" in result
        gw.scroll.assert_called_once_with("session", 500)

    @pytest.mark.asyncio
    async def test_wait(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.WAIT, ("#target", "5"), session_name=self.SESSION_NAME
        )
        assert "#target" in result
        gw.wait_for.assert_called_once_with("session", "#target", 5.0)

    @pytest.mark.asyncio
    async def test_clear_cookies(self) -> None:
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.CLEAR_COOKIES, (), session_name=self.SESSION_NAME
        )
        assert "Cookies cleared" in result
        gw.clear_cookies.assert_called_once_with("session")

    @pytest.mark.asyncio
    async def test_switchtab_persists_target(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        session_file = tmp_path / f"{self.SESSION_NAME}.json"
        session_file.write_text(json.dumps({"host": "localhost", "port": 9222}))
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        await dispatch(
            gw, Command.SWITCHTAB, ("t2",), session_name=self.SESSION_NAME
        )
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
        session_file = tmp_path / "myagent.json"
        session_file.write_text(
            json.dumps({"host": "localhost", "port": 9222, "target_id": "t3"})
        )
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        gw = _make_gateway()
        await dispatch(gw, Command.INFO, (), session_name="myagent")
        from browsectl.models import BrowserEndpoint
        gw.connect.assert_called_once_with(
            BrowserEndpoint(host="localhost", port=9222), "t3"
        )


class TestParseLaunchArgs:
    def test_no_args_returns_none_port(self) -> None:
        port, host = _parse_launch_args(())
        assert port is None
        assert host == "localhost"

    def test_explicit_port(self) -> None:
        port, host = _parse_launch_args(("9222",))
        assert port == 9222
        assert host == "localhost"

    def test_port_with_host(self) -> None:
        port, host = _parse_launch_args(("9333", "--host", "remote.dev"))
        assert port == 9333
        assert host == "remote.dev"

    def test_host_only_no_port(self) -> None:
        port, host = _parse_launch_args(("--host", "mybox"))
        assert port is None
        assert host == "mybox"

    def test_invalid_port(self) -> None:
        with pytest.raises(SystemExit, match="Invalid port"):
            _parse_launch_args(("abc",))

    def test_host_without_value(self) -> None:
        with pytest.raises(SystemExit, match="--host requires"):
            _parse_launch_args(("9222", "--host"))


class TestCheckPortFree:
    def test_free_port(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
        sock.close()
        _check_port_free("127.0.0.1", port)

    def test_port_in_use(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
        sock.listen(1)
        try:
            with pytest.raises(SystemExit, match="already in use"):
                _check_port_free("127.0.0.1", port)
        finally:
            sock.close()


class TestDispatchLaunch:
    @pytest.mark.asyncio
    async def test_launch_saves_session(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        monkeypatch.setattr("browsectl.core.LAUNCH_TIMEOUT", 2.0)
        monkeypatch.setattr("browsectl.core.LAUNCH_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(
            "browsectl.core._check_port_free", lambda _h, _p: None
        )

        gw = _make_gateway()
        result = await dispatch(
            gw, Command.LAUNCH, ("9333",), session_name="agent1"
        )
        assert "9333" in result
        assert "12345" in result

        session_file = tmp_path / "agent1.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["host"] == "localhost"
        assert data["port"] == 9333

        gw.launch_browser.assert_called_once_with("agent1", 9333)

    @pytest.mark.asyncio
    async def test_launch_auto_port(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        monkeypatch.setattr("browsectl.core.LAUNCH_TIMEOUT", 2.0)
        monkeypatch.setattr("browsectl.core.LAUNCH_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(
            "browsectl.core._find_free_port", lambda _h: 44321
        )

        gw = _make_gateway()
        result = await dispatch(
            gw, Command.LAUNCH, (), session_name="auto1"
        )
        assert "44321" in result

        session_file = tmp_path / "auto1.json"
        data = json.loads(session_file.read_text())
        assert data["port"] == 44321

        gw.launch_browser.assert_called_once_with("auto1", 44321)

    @pytest.mark.asyncio
    async def test_launch_port_in_use_fails(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
        sock.listen(1)
        try:
            gw = _make_gateway()
            with pytest.raises(SystemExit, match="already in use"):
                await dispatch(
                    gw, Command.LAUNCH, (str(port),),
                    session_name="blocked"
                )
        finally:
            sock.close()

    @pytest.mark.asyncio
    async def test_launch_with_host_override(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        monkeypatch.setattr("browsectl.core.LAUNCH_TIMEOUT", 2.0)
        monkeypatch.setattr("browsectl.core.LAUNCH_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(
            "browsectl.core._check_port_free", lambda _h, _p: None
        )

        gw = _make_gateway()
        result = await dispatch(
            gw, Command.LAUNCH, ("9444", "--host", "mybox"),
            session_name="remote1"
        )
        assert "mybox:9444" in result

        session_file = tmp_path / "remote1.json"
        data = json.loads(session_file.read_text())
        assert data["host"] == "mybox"

    @pytest.mark.asyncio
    async def test_launch_saves_pid(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        monkeypatch.setattr("browsectl.core.LAUNCH_TIMEOUT", 2.0)
        monkeypatch.setattr("browsectl.core.LAUNCH_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(
            "browsectl.core._check_port_free", lambda _h, _p: None
        )

        gw = _make_gateway()
        await dispatch(
            gw, Command.LAUNCH, ("9333",), session_name="pidtest"
        )

        session_file = tmp_path / "pidtest.json"
        data = json.loads(session_file.read_text())
        assert data["pid"] == 12345


class TestStopSession:
    def test_stops_running_process(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        session_file = tmp_path / "agent1.json"
        session_file.write_text(
            json.dumps({"host": "localhost", "port": 9333, "pid": 99999999})
        )
        result = stop_session("agent1")
        assert "agent1" in result
        assert "99999999" in result
        assert not session_file.exists()

    def test_stops_without_pid(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        session_file = tmp_path / "nopid.json"
        session_file.write_text(
            json.dumps({"host": "localhost", "port": 9333})
        )
        result = stop_session("nopid")
        assert "no associated process" in result
        assert not session_file.exists()

    def test_stop_does_not_affect_other_sessions(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        agent1_file = tmp_path / "agent1.json"
        agent2_file = tmp_path / "agent2.json"
        agent1_file.write_text(
            json.dumps({"host": "localhost", "port": 9333, "pid": 99999999})
        )
        agent2_file.write_text(
            json.dumps({"host": "localhost", "port": 9444, "pid": 88888888})
        )

        stop_session("agent1")

        assert not agent1_file.exists()
        assert agent2_file.exists()
        data = json.loads(agent2_file.read_text())
        assert data["pid"] == 88888888
        assert data["port"] == 9444

    def test_no_session_fails(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        with pytest.raises(SystemExit, match="No session"):
            stop_session("ghost")

    @pytest.mark.asyncio
    async def test_dispatch_stop(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        session_file = tmp_path / "stopme.json"
        session_file.write_text(
            json.dumps({"host": "localhost", "port": 9333, "pid": 99999999})
        )
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.STOP, (), session_name="stopme"
        )
        assert "Stopped" in result
        assert not session_file.exists()


class TestListSessions:
    def test_no_sessions_dir(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path / "missing")
        assert list_sessions() == "(no sessions)"

    def test_empty_dir(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        assert list_sessions() == "(no sessions)"

    def test_lists_multiple_sessions(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        (tmp_path / "alpha.json").write_text(
            json.dumps({"host": "localhost", "port": 9222, "pid": 99999999})
        )
        (tmp_path / "beta.json").write_text(
            json.dumps({"host": "mybox", "port": 9333})
        )
        result = list_sessions()
        assert "alpha" in result
        assert "localhost:9222" in result
        assert "beta" in result
        assert "mybox:9333" in result
        assert "external" in result

    def test_dead_process_shown_as_dead(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        (tmp_path / "stale.json").write_text(
            json.dumps({"host": "localhost", "port": 9222, "pid": 99999999})
        )
        result = list_sessions()
        assert "dead" in result

    def test_corrupt_file_handled(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        (tmp_path / "broken.json").write_text("not json{{{")
        result = list_sessions()
        assert "broken" in result
        assert "corrupt" in result

    @pytest.mark.asyncio
    async def test_dispatch_sessions(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr("browsectl.core.SESSIONS_DIR", tmp_path)
        (tmp_path / "myagent.json").write_text(
            json.dumps({"host": "localhost", "port": 9222, "pid": 99999999})
        )
        gw = _make_gateway()
        result = await dispatch(
            gw, Command.SESSIONS, (), session_name=""
        )
        assert "myagent" in result
