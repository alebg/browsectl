"""Desktop environment adapter: keep browser windows from stealing focus.

On KDE (KWin), installs one persistent window rule that matches every
window whose class starts with WM_CLASS_PREFIX and forces focus stealing
prevention to its strictest level. The rule overrides the global level, so
it works even when the user has focus stealing prevention switched off.
"""

import logging
import os
import shutil
import subprocess

from browsectl.models import WM_CLASS_PREFIX

logger = logging.getLogger(__name__)

RULES_FILE = "kwinrulesrc"
GENERAL_GROUP = "General"
RULES_KEY = "rules"
COUNT_KEY = "count"
RULE_GROUP = "browsectl-no-focus"
FSP_LEVEL_EXTREME = "4"
RULE_FORCE = "2"
MATCH_REGEX = "3"


def _is_kde() -> bool:
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def _kconfig(tool: str, *args: str) -> str:
    result = subprocess.run(
        (tool, "--file", RULES_FILE, *args),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write_key(group: str, key: str, value: str, kind: str = "string") -> None:
    _kconfig(
        "kwriteconfig5", "--group", group, "--type", kind, "--key", key, value
    )


def _set_registered_rules(rules: tuple[str, ...]) -> None:
    """Write the list of active rule groups and the matching count."""
    _write_key(GENERAL_GROUP, RULES_KEY, ",".join(rules))
    _write_key(GENERAL_GROUP, COUNT_KEY, str(len(rules)), "int")


def _reload_kwin() -> None:
    subprocess.run(
        ("qdbus", "org.kde.KWin", "/KWin", "reconfigure"),
        capture_output=True,
        check=True,
    )


def ensure_no_focus_rule() -> bool:
    """Install the no-focus KWin rule if missing. Returns True if in place.

    Idempotent: does nothing when the rule is already registered. Never
    raises; on unsupported desktops or tool failures it logs a warning and
    returns False so the launch can proceed. If KWin cannot be reloaded, the
    rule is unregistered again, so the next launch retries the install and
    reload instead of trusting a rule KWin never loaded.
    """
    tools = ("kreadconfig5", "kwriteconfig5", "qdbus")
    if not _is_kde() or any(shutil.which(t) is None for t in tools):
        logger.warning(
            "Cannot prevent focus stealing: needs KDE with %s. "
            "Windows launched with --foreground may take focus.",
            ", ".join(tools),
        )
        return False
    try:
        rules = tuple(
            r for r in _kconfig(
                "kreadconfig5", "--group", GENERAL_GROUP, "--key", RULES_KEY
            ).split(",") if r
        )
        if RULE_GROUP in rules:
            return True
        _write_key(RULE_GROUP, "Description", "browsectl: never take focus")
        _write_key(RULE_GROUP, "fsplevel", FSP_LEVEL_EXTREME, "int")
        _write_key(RULE_GROUP, "fsplevelrule", RULE_FORCE, "int")
        _write_key(RULE_GROUP, "wmclass", f"^{WM_CLASS_PREFIX}.*")
        _write_key(RULE_GROUP, "wmclasscomplete", "false", "bool")
        _write_key(RULE_GROUP, "wmclassmatch", MATCH_REGEX, "int")
        # Register the group last so a partial write never becomes active.
        _set_registered_rules((*rules, RULE_GROUP))
        try:
            _reload_kwin()
        except (subprocess.CalledProcessError, OSError):
            _set_registered_rules(rules)
            raise
    except (subprocess.CalledProcessError, OSError):
        logger.warning("Failed to install KWin no-focus rule", exc_info=True)
        return False
    return True
