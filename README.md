# browsectl

Browser-agnostic automation for AI agents.

A lightweight CLI that lets AI agents (or humans) drive a real browser session: navigate, screenshot, click, type, extract DOM, and evaluate JavaScript. Designed so that agents can see client-side-rendered pages (like LinkedIn) that aren't curl-friendly.

## How it works

You launch your browser with remote debugging enabled. `browsectl` connects to it and sends commands over the browser's native automation protocol. The agent takes screenshots to "see" the page and decides what to do next. When it hits a CAPTCHA or 2FA wall, it tells you and waits.

The core is browser-agnostic. Concrete browser support is provided by swappable backends (currently: CDP for Chrome/Chromium).

## Requirements

- Python 3.14+
- Chrome or Chromium (for the CDP backend)

## Installation

```bash
git clone <repo-url>
cd browsectl
python -m venv .venv
.venv/bin/pip install poetry
.venv/bin/poetry install
```

## Quick start

### 1. Launch Chrome with remote debugging

Symlink the launcher into your PATH once:

```bash
ln -sf /path/to/browsectl/bin/browsectl-chrome ~/.local/bin/browsectl-chrome
```

Then just run:

```bash
browsectl-chrome
```

This opens a separate Chrome instance with its own profile at `~/.browsectl/chrome-profile/`. Logins persist across sessions. Your existing Chrome windows are unaffected.

Alternatively, launch manually:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.browsectl/chrome-profile"
```

### 2. Connect

```bash
browsectl connect              # defaults to localhost:9222
browsectl connect myhost 9333  # custom host/port
```

### 3. Use it

```bash
browsectl goto "https://example.com"
browsectl screenshot                    # saves screenshot.png
browsectl screenshot /tmp/page.png      # custom path
browsectl info                          # current URL and title
browsectl html "h1"                     # extract innerHTML
browsectl eval "document.title"         # run JavaScript
browsectl click "#login-button"         # click by CSS selector
browsectl type "#email" "me@example.com"
browsectl scroll 500                    # scroll down 500px
browsectl scroll -300                   # scroll up 300px
browsectl wait ".results" 10            # wait for element (10s timeout)
browsectl tabs                          # list open tabs
browsectl newtab "https://github.com"   # open new tab
browsectl switchtab <tab-id>            # switch to tab (ID from 'tabs')
```

## Named sessions

Run multiple independent browser sessions simultaneously:

```bash
browsectl -s linkedin connect localhost 9222
browsectl -s linkedin goto "https://linkedin.com/feed/"
browsectl -s research connect otherhost 9333
```

Each session stores its own endpoint and active tab in `~/.browsectl/sessions/<name>.json`. Default session name is `default`.

## Backend selection

```bash
browsectl -b cdp goto "https://example.com"   # explicit (default)
```

Available backends: `cdp`. The architecture supports adding others (WebDriver, Marionette, etc.) without changing the core.

## Architecture

Hexagonal / ports-and-adapters. The core never imports a concrete browser adapter.

```
browsectl/
  models.py       # domain types (PageInfo, Screenshot, Tab, etc.)
  ports.py         # function signature contracts, generic over Session
  gateway.py       # BrowserGateway[S] -- frozen bundle of port functions
  core.py          # command dispatch, browser-agnostic
  main.py          # CLI entry point, wiring
  adapters/
    cdp.py         # Chrome DevTools Protocol implementation
```

## Per-site guides

`docs/sites/` contains navigation guides for specific websites. Each guide documents working selectors, SPA quirks, authentication patterns, and step-by-step browsectl workflows for that site. Selectors are timestamped since sites change their DOM frequently.

Use `docs/sites/_template.md` as a starting point for new guides.

## Development

```bash
.venv/bin/pytest tests/ -v       # run tests
.venv/bin/mypy browsectl/        # type check (strict)
.venv/bin/ruff check browsectl/  # lint
```

## License

MIT. See [LICENSE](LICENSE).
