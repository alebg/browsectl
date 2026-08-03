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

Sends SIGTERM to the Chrome process and removes the session file. Other sessions are unaffected.

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
