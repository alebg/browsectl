"""Domain types for browsectl."""

from enum import StrEnum

import attrs


@attrs.define(frozen=True, slots=True)
class BrowserEndpoint:
    """Where to connect to a browser's automation interface."""

    host: str
    port: int


@attrs.define(frozen=True, slots=True)
class Tab:
    """A single browser tab."""

    id: str
    title: str
    url: str


@attrs.define(frozen=True, slots=True)
class PageInfo:
    """Current state of a page."""

    url: str
    title: str


@attrs.define(frozen=True, slots=True)
class Screenshot:
    """Captured page image."""

    data: bytes
    format: str


@attrs.define(frozen=True, slots=True)
class EvalResult:
    """Result of evaluating a JS expression."""

    value: str


class Command(StrEnum):
    """CLI commands."""

    CONNECT = "connect"
    GOTO = "goto"
    SCREENSHOT = "screenshot"
    CLICK = "click"
    TYPE = "type"
    HTML = "html"
    EVAL = "eval"
    INFO = "info"
    TABS = "tabs"
    NEWTAB = "newtab"
    SWITCHTAB = "switchtab"
