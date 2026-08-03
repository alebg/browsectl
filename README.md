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

### 1. Launch and connect (one step)

```bash
browsectl -s myagent launch
```

This auto-assigns a free port, starts Chrome with its own profile at `~/.browsectl/profiles/myagent/`, waits for CDP readiness, connects, and saves the session. The port is stored in the session file so all subsequent commands find it automatically. Logins persist across runs. Your existing Chrome windows are unaffected.

You can also specify a port explicitly if needed:

```bash
browsectl -s myagent launch 9500
```

If the explicit port is already in use, `launch` fails immediately with a clear error.

### 2. Use it

Every command requires `-s <session>`:

```bash
browsectl -s myagent goto "https://example.com"
browsectl -s myagent screenshot                    # saves screenshot.png
browsectl -s myagent screenshot /tmp/page.png      # custom path
browsectl -s myagent info                          # current URL and title
browsectl -s myagent html "h1"                     # extract innerHTML
browsectl -s myagent eval "document.title"         # run JavaScript
browsectl -s myagent click "#login-button"         # click by CSS selector
browsectl -s myagent type "#email" "me@example.com"
browsectl -s myagent scroll 500                    # scroll down 500px
browsectl -s myagent scroll -300                   # scroll up 300px
browsectl -s myagent wait ".results" 10            # wait for element (10s timeout)
browsectl -s myagent tabs                          # list open tabs
browsectl -s myagent newtab "https://github.com"   # open new tab
browsectl -s myagent switchtab <tab-id>            # switch to tab (ID from 'tabs')
browsectl -s myagent clear-cookies                 # clear all browser cookies
```

### Connecting to an existing browser

If Chrome is already running with `--remote-debugging-port`, use `connect` instead of `launch`:

```bash
browsectl -s myagent connect localhost 9500
```

Both host and port are required.

## Multiple sessions

Run multiple independent browser sessions simultaneously. Each gets its own auto-assigned port:

```bash
browsectl -s agent1 launch
browsectl -s agent2 launch
browsectl -s agent1 goto "https://example.com"
browsectl -s agent2 goto "https://github.com"
```

Each session gets its own Chrome process, profile directory, cookies, and localStorage. Ports are auto-assigned so agents never clash. See `docs/multi-session.md` for details.

## Standalone Chrome launcher

The `bin/browsectl-chrome` script launches Chrome without connecting. Useful when you want to manage Chrome separately:

```bash
browsectl-chrome myprofile 9500
```

Both profile name and port are required.

## Backend selection

```bash
browsectl -s myagent -b cdp goto "https://example.com"   # explicit (default)
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
