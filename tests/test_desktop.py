"""Tests for the KWin no-focus rule installer."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from browsectl.adapters.desktop import RULE_GROUP, ensure_no_focus_rule


def _run_returning(rules: str) -> MagicMock:
    mock = MagicMock()
    mock.return_value.stdout = rules
    return mock


def _commands(mock: MagicMock) -> list[tuple[str, ...]]:
    return [call.args[0] for call in mock.call_args_list]


class TestEnsureNoFocusRule:
    def test_skips_on_non_kde(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
        run = _run_returning("")
        with patch("browsectl.adapters.desktop.subprocess.run", run):
            assert ensure_no_focus_rule() is False
        run.assert_not_called()

    def test_noop_when_rule_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
        run = _run_returning(f"1,2,{RULE_GROUP}")
        with (
            patch("browsectl.adapters.desktop.shutil.which", MagicMock()),
            patch("browsectl.adapters.desktop.subprocess.run", run),
        ):
            assert ensure_no_focus_rule() is True
        assert all(c[0] == "kreadconfig5" for c in _commands(run))

    def test_installs_rule_then_reloads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
        run = _run_returning("1,2")
        with (
            patch("browsectl.adapters.desktop.shutil.which", MagicMock()),
            patch("browsectl.adapters.desktop.subprocess.run", run),
        ):
            assert ensure_no_focus_rule() is True
        commands = _commands(run)
        assert commands[-1][0] == "qdbus"
        rules_write = next(
            c for c in commands if c[0] == "kwriteconfig5" and "rules" in c
        )
        assert rules_write[-1] == f"1,2,{RULE_GROUP}"
        # The group must be registered after its keys are written.
        group_writes = [
            i for i, c in enumerate(commands)
            if "--group" in c and c[c.index("--group") + 1] == RULE_GROUP
        ]
        assert group_writes
        assert commands.index(rules_write) > max(group_writes)

    def test_unregisters_rule_when_reload_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rule KWin never loaded must not look installed on the next launch."""
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")

        def fake_run(cmd: tuple[str, ...], **_kwargs: object) -> MagicMock:
            if cmd[0] == "qdbus":
                raise subprocess.CalledProcessError(1, cmd)
            result = MagicMock()
            result.stdout = "1,2"
            return result

        run = MagicMock(side_effect=fake_run)
        with (
            patch("browsectl.adapters.desktop.shutil.which", MagicMock()),
            patch("browsectl.adapters.desktop.subprocess.run", run),
        ):
            assert ensure_no_focus_rule() is False
        rules_writes = [
            c for c in _commands(run)
            if c[0] == "kwriteconfig5" and "rules" in c
        ]
        assert [c[-1] for c in rules_writes] == [f"1,2,{RULE_GROUP}", "1,2"]
