"""Browser gateway bundle -- the single injection point for core."""

import attrs

from browsectl.ports import (
    TClick,
    TConnect,
    TDisconnect,
    TEvalJs,
    TExtractHtml,
    TListTabs,
    TNavigate,
    TPageInfo,
    TScreenshot,
    TTypeText,
)


@attrs.define(frozen=True, slots=True)
class BrowserGateway[S]:
    """Bundles all browser port functions into a single injectable unit."""

    connect: TConnect[S]
    disconnect: TDisconnect[S]
    navigate: TNavigate[S]
    screenshot: TScreenshot[S]
    click: TClick[S]
    type_text: TTypeText[S]
    extract_html: TExtractHtml[S]
    eval_js: TEvalJs[S]
    page_info: TPageInfo[S]
    list_tabs: TListTabs[S]
