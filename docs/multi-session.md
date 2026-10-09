# Running Multiple browsectl Sessions Concurrently

browsectl supports multiple independent users (human, Claude agents, CI) driving Chrome at the same time. Each session gets its own Chrome instance on a separate port with a separate profile directory.

## Setup

Each session uses the `launch` command with a unique session name. Ports are auto-assigned so agents never clash:

```bash
browsectl -s <session-a> launch
browsectl -s <session-b> launch
browsectl -s <session-c> launch
```

Each `launch` call:
1. Finds a free ephemeral port (or checks the explicit port is free, if one was provided)
2. Starts Chrome with `--remote-debugging-port=<port>` and `--user-data-dir=~/.browsectl/profiles/<session>/`
3. Waits for CDP readiness
4. Saves the connection info (including port) to `~/.browsectl/sessions/<session>.json`

## Using sessions

Every command requires the `-s` flag to target the correct session:

```bash
browsectl -s <session-a> goto "https://example.com"
browsectl -s <session-a> screenshot output.png

browsectl -s <session-b> goto "https://github.com"
browsectl -s <session-b> info
```

## Port assignment

By default, `launch` auto-assigns a free port from the OS ephemeral range. You can also specify a port explicitly:

```bash
browsectl -s <session> launch <port>
```

If the explicit port is already in use, `launch` fails immediately:

```
$ browsectl -s <session> launch <port>
Port <port> is already in use on localhost.
Choose a different port or stop the existing process.
```

## Why separate Chrome instances?

- **Separate profiles** prevent cookie/login conflicts. Each Chrome has its own cookies, localStorage, and history.
- **Separate ports** prevent CDP command conflicts. Each browsectl session talks to its own Chrome over its own WebSocket.
- **The `-s` flag** keeps browsectl's internal session state (which tab is active, connection info) separate per named session.

Using only the `-s` flag with `newtab` on a shared Chrome instance is NOT enough. Commands like `goto` and `screenshot` can race with each other and interfere across sessions.

## Connecting to existing Chrome instances

If Chrome is already running (started manually or by another tool), use `connect` instead of `launch`:

```bash
browsectl -s <session> connect <host> <port>
```

Both host and port are required.

## Listing sessions

```bash
browsectl sessions
```

Shows every saved session with its name, host:port, PID, and status:
- **running**: the Chrome process is alive
- **dead**: the process has exited but the session file remains
- **external**: connected via `connect` (no PID tracked)

Use `--prune` to remove stale (dead/external) session files.

No `-s` flag required.

## Stopping sessions

```bash
browsectl -s <session> stop      # stop one session
browsectl stop-all               # stop all sessions at once
```

Sends SIGTERM to the session's whole process group (the Chrome process, its helpers, and the Xvfb server in the default mode) and removes the session file. Other sessions are unaffected.

Each browser is launched in its own process group, which is what makes this possible. Sessions saved by older versions hold a plain Chrome or `xvfb-run` pid instead; for those, `stop` kills only that one pid, so Xvfb-mode sessions from before this change can leave Chrome and Xvfb running. Relaunch them to get the new behavior.

The session's pid is preserved across `switchtab`. Before this was fixed, `switchtab` dropped the pid from the session file and a later `stop` removed the file without killing Chrome.

## Window focus with `--foreground`

By default each Chrome runs inside Xvfb, so no window ever appears on your desktop. With `--foreground` the window is shown, and a window manager will normally give a newly mapped window keyboard focus. With several agents working in parallel that is disruptive, so browsectl is designed so that no command takes focus from the window you are using.

What enforces this:

- **Window class.** Chrome is launched with `--class=browsectl-<session>`, so every browsectl window has a predictable `WM_CLASS`.
- **KWin rule (KDE on X11).** On the first `launch --foreground`, browsectl adds a rule named `browsectl-no-focus` to `~/.config/kwinrulesrc` and asks KWin to reload. The rule matches the regex `^browsectl-.*` and forces focus stealing prevention to its strictest level (4), which overrides the global setting even if it is switched off. It is installed once; later launches find it and do nothing. You can see or remove it under System Settings, Window Management, Window Rules.
- **Background tabs.** `newtab` creates tabs with `background: true`, so Chrome does not activate them.

Verified on KDE Plasma 5.27 / X11 with focus stealing prevention set to 0 globally: with the rule, launching Chrome and then running goto, click, hover, click-xy, click-text, type, drag, scroll, resize, screenshot, eval, info, html, newtab, tabs, switchtab and clear-cookies never made a browsectl window the active window. Without the rule, a launched Chrome took focus. You can still click a browsectl window and type in it normally.

Limits:

- Only KDE with `kreadconfig5`, `kwriteconfig5` and `qdbus` is handled. On any other desktop, `launch --foreground` logs a warning and the window may take focus. Use the default Xvfb mode there.
- Sessions launched before this change have no class, so the rule cannot match them. Stop and relaunch them.
- Not tested: two sessions making their very first `--foreground` launch at the same instant (both would try to install the rule), and Wayland sessions.

To re-check after a change, `scripts/focus_audit.sh` runs every command against a foreground session and reports any that make a browsectl window active. Leave your desktop alone while it runs (about a minute), because it needs a window to pop up. `scripts/focus_probe.sh <class>` tests a single launch with a given window class, and `scripts/stop_probe.sh` checks that `stop` leaves no processes behind.

## Launch timeout

The `launch` command waits up to 15 seconds for Chrome's CDP endpoint to become ready. Override with `--timeout`:

```bash
browsectl -s <session> launch --timeout 30
```

## Cleanup

Profile directories persist at `~/.browsectl/profiles/<session>/` so logins survive across runs. To list and clean up orphaned profiles:

```bash
browsectl profiles              # list all profiles (active/orphaned)
browsectl profiles --prune      # remove orphaned profile directories
```
