"""Function signature contracts for browser operations."""

from collections.abc import Awaitable, Callable

from browsectl.models import (
    BrowserEndpoint,
    EvalResult,
    PageInfo,
    Screenshot,
    Tab,
)

type TConnect[S] = Callable[[BrowserEndpoint], Awaitable[S]]
type TDisconnect[S] = Callable[[S], Awaitable[None]]
type TNavigate[S] = Callable[[S, str], Awaitable[PageInfo]]
type TScreenshot[S] = Callable[[S], Awaitable[Screenshot]]
type TClick[S] = Callable[[S, str], Awaitable[None]]
type TTypeText[S] = Callable[[S, str, str], Awaitable[None]]
type TExtractHtml[S] = Callable[[S, str], Awaitable[str]]
type TEvalJs[S] = Callable[[S, str], Awaitable[EvalResult]]
type TPageInfo[S] = Callable[[S], Awaitable[PageInfo]]
type TListTabs[S] = Callable[[S], Awaitable[tuple[Tab, ...]]]
type TNewTab[S] = Callable[[S, str], Awaitable[Tab]]
type TSwitchTab[S] = Callable[[S, str], Awaitable[None]]
