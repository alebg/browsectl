"""Function signature contracts for browser operations."""

import subprocess
from collections.abc import Awaitable, Callable

from browsectl.models import (
    BrowserEndpoint,
    EvalResult,
    PageInfo,
    Screenshot,
    Tab,
)

type TConnect[S] = Callable[[BrowserEndpoint, str | None], Awaitable[S]]
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
type TScroll[S] = Callable[[S, int], Awaitable[None]]
type TWaitFor[S] = Callable[[S, str, float], Awaitable[None]]
type TClearCookies[S] = Callable[[S], Awaitable[None]]
type TClickXy[S] = Callable[[S, float, float], Awaitable[None]]
type THover[S] = Callable[[S, str], Awaitable[None]]
type TClickText[S] = Callable[[S, str], Awaitable[None]]
type TDrag[S] = Callable[[S, float, float, float, float], Awaitable[None]]
type TResize[S] = Callable[[S, int, int], Awaitable[None]]
type TLaunchBrowser = Callable[[str, int, bool], subprocess.Popen[bytes]]
type TConfigureBrowser = Callable[[BrowserEndpoint], Awaitable[None]]
