#!/usr/bin/env bash
# Launch a throwaway Chrome with --class=<wmclass> on the current X11 display
# and report whether the active window changed. Usage: focus_probe.sh <wmclass>
set -u
cls="${1:?usage: focus_probe.sh <wmclass>}"
# Ask the OS for a free port so concurrent sessions never collide.
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
profile="$(mktemp -d)"

active() { xprop -root _NET_ACTIVE_WINDOW | awk '{print $NF}'; }
clients() { xprop -root _NET_CLIENT_LIST | sed 's/.*# //; s/, / /g'; }

before_active="$(active)"
before_clients="$(clients)"
echo "active before: $before_active"

google-chrome --class="$cls" --user-data-dir="$profile" \
  --remote-debugging-port="$port" --no-first-run about:blank \
  >/dev/null 2>&1 &
pid=$!

seen=""
for _ in $(seq 1 40); do
  sleep 0.2
  now="$(active)"
  case " $seen " in *" $now "*) ;; *) seen="$seen $now" ;; esac
done
echo "active ids seen during launch:$seen"

for w in $(clients); do
  case " $before_clients " in *" $w "*) continue ;; esac
  echo "new window $w: $(xprop -id "$w" WM_CLASS)"
done

after_active="$(active)"
echo "active after: $after_active"
if [ "$before_active" = "$after_active" ] && [ "$seen" = " $before_active" ]; then
  echo "RESULT: focus NOT stolen"
else
  echo "RESULT: focus CHANGED"
fi

kill "$pid" 2>/dev/null
pkill -f -- "--user-data-dir=$profile" 2>/dev/null
sleep 1
rm -rf "$profile"
