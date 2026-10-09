"""Tests for the CLI wiring in main.py."""

from unittest.mock import MagicMock, patch

import pytest

from browsectl.main import _launch_cdp_browser


class TestLaunchCdpBrowser:
    @pytest.mark.parametrize("foreground", [True, False])
    def test_rule_installed_only_for_foreground(self, foreground: bool) -> None:
        ensure = MagicMock()
        launch = MagicMock()
        with (
            patch("browsectl.main.desktop.ensure_no_focus_rule", ensure),
            patch("browsectl.main.cdp.launch_browser", launch),
        ):
            result = _launch_cdp_browser("agent1", 9333, foreground)

        assert ensure.call_count == (1 if foreground else 0)
        launch.assert_called_once_with("agent1", 9333, foreground)
        assert result is launch.return_value

    def test_rule_is_installed_before_launch(self) -> None:
        calls: list[str] = []
        ensure = MagicMock(side_effect=lambda: calls.append("ensure"))
        launch = MagicMock(side_effect=lambda *_a: calls.append("launch"))
        with (
            patch("browsectl.main.desktop.ensure_no_focus_rule", ensure),
            patch("browsectl.main.cdp.launch_browser", launch),
        ):
            _launch_cdp_browser("agent1", 9333, True)

        assert calls == ["ensure", "launch"]
