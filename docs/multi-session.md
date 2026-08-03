# Running Multiple browsectl Sessions Concurrently

browsectl supports multiple independent users (human, Claude agents, CI) driving Chrome at the same time. Each session gets its own Chrome instance on a separate port with a separate profile directory.

## Setup

Each session uses the `launch` command with a unique session name and port:

```bash
# First session
browsectl -s agent1 launch 9222

# Second session
browsectl -s agent2 launch 9333

# Third session
browsectl -s agent3 launch 9444
```

Each `launch` call:
1. Checks the port is free (fails immediately if occupied)
2. Starts Chrome with `--remote-debugging-port=<port>` and `--user-data-dir=~/.browsectl/profiles/<session>/`
3. Waits for CDP readiness
4. Saves the connection info to `~/.browsectl/sessions/<session>.json`

## Using sessions

Every command requires the `-s` flag to target the correct session:

```bash
browsectl -s agent1 goto "https://example.com"
browsectl -s agent1 screenshot output.png

browsectl -s agent2 goto "https://github.com"
browsectl -s agent2 info
```

## Port conflict detection

If an agent tries to launch on a port that is already in use, `launch` fails immediately:

```
$ browsectl -s agent3 launch 9222
Port 9222 is already in use on localhost.
Choose a different port or stop the existing process.
```

This prevents accidental sharing of Chrome instances between agents.

## Why separate Chrome instances?

- **Separate profiles** prevent cookie/login conflicts. Each Chrome has its own cookies, localStorage, and history.
- **Separate ports** prevent CDP command conflicts. Each browsectl session talks to its own Chrome over its own WebSocket.
- **The `-s` flag** keeps browsectl's internal session state (which tab is active, connection info) separate per named session.

Using only the `-s` flag with `newtab` on a shared Chrome instance is NOT enough. Commands like `goto` and `screenshot` can race with each other and interfere across sessions.

## Connecting to existing Chrome instances

If Chrome is already running (started manually or by another tool), use `connect` instead of `launch`:

```bash
browsectl -s legacy connect localhost 9222
```

Both host and port are required.

## Standalone launcher

The `bin/browsectl-chrome` script launches Chrome without connecting. Useful for manual setups:

```bash
browsectl-chrome myprofile 9222
```

Both profile name and port are required. Profiles are stored at `~/.browsectl/profiles/<name>/`.

## Cleanup

Kill Chrome instances by port when done:

```bash
pkill -f "remote-debugging-port=9333"
```

Profile directories persist at `~/.browsectl/profiles/<name>/` so logins survive across runs. Remove them manually if no longer needed.
