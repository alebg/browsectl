#!/usr/bin/env bash
# Run every browsectl command against a --foreground session on X11 and report
# which ones change the active window. Leave the desktop alone while it runs
# (about a minute), otherwise your own window switches count as steals.
set -u
BC="${BC:-.venv/bin/browsectl}"
S="focus-audit"
page='data:text/html,<button id=b onclick="document.title=1">Go</button><input id=i><p>hello</p>'
log="$(mktemp)"

active() { xprop -root _NET_ACTIVE_WINDOW | awk '{print $NF}'; }
mark() { echo "$(date +%s.%N) MARK $*" >>"$log"; }

baseline="$(active)"
(
  prev=""
  while :; do
    now="$(active)"
    if [ "$now" != "$prev" ]; then
      cls="$(xprop -id "$now" WM_CLASS 2>/dev/null | sed 's/.*= //; s/ /_/g')"
      echo "$(date +%s.%N) ACTIVE $now $cls" >>"$log"
      prev="$now"
    fi
    sleep 0.05
  done
) &
poller=$!
trap 'kill $poller 2>/dev/null; $BC -s $S stop >/dev/null 2>&1' EXIT

run() { mark "$1"; shift; "$BC" -s "$S" "$@" >/dev/null 2>&1; sleep 0.7; }

run launch launch --foreground
run goto goto "$page"
run click click '#b'
run hover hover '#b'
run click-xy click-xy 50 50
run click-text click-text Go
run type type '#i' hello
run drag drag 10 10 100 100
run scroll scroll 100
run resize resize 800 600
run screenshot screenshot /dev/null
run eval eval 'document.title'
run info info
run html html p
run newtab newtab about:blank
mark tabs
tabs_out="$("$BC" -s "$S" tabs 2>/dev/null)"
tab_id="$(echo "$tabs_out" | grep -oE '^[0-9A-F]{32}' | tail -1)"
if [ -n "$tab_id" ]; then
  run switchtab switchtab "$tab_id"
else
  echo "WARNING: switchtab not tested; tabs output was: [$tabs_out]"
fi
run clear-cookies clear-cookies
run stop stop
mark end

kill $poller 2>/dev/null
echo "baseline active window: $baseline"
# Only a browsectl-* window becoming active counts. Switches between your own
# windows while the audit runs are ignored.
awk '
  $2 == "MARK" { phase = $3; if (!(phase in seen)) { order[++n] = phase; seen[phase] = 1 }; next }
  $2 == "ACTIVE" && phase != "" && $4 ~ /browsectl-/ { bad[phase]++ }
  END {
    for (i = 1; i <= n; i++) {
      p = order[i]
      printf "%-13s %s\n", p, (bad[p] ? "STOLE FOCUS (" bad[p] "x)" : "ok")
    }
  }' "$log"
echo "full log: $log"
