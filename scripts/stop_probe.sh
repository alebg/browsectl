#!/usr/bin/env bash
# Bisect which command sequences make `browsectl stop` leave processes behind.
# Each case launches a --foreground session, runs some commands, stops it, and
# counts survivors in the session's process group. Survivors are SIGKILLed.
set -u
BC="${BC:-.venv/bin/browsectl}"
# No spaces or quotes: the cases below are word-split on purpose.
page='data:text/html,<button/id=b/onclick=document.title=1>Go</button><input/id=i><p>hello</p>'

probe() {
  local s="stopprobe-$1"; shift
  timeout 40 "$BC" -s "$s" launch --foreground >/dev/null 2>&1
  local pid
  pid="$(jq -r .pid ~/.browsectl/sessions/$s.json)"
  while [ $# -gt 0 ]; do
    # shellcheck disable=SC2086
    "$BC" -s "$s" $1 >/dev/null 2>&1
    shift
  done
  sleep 1
  local t0 t1
  t0="$(date +%s.%N)"
  "$BC" -s "$s" stop >/dev/null 2>&1
  t1="$(date +%s.%N)"
  sleep 1
  echo "$s: stop took $(echo "$t1 - $t0" | bc)s, group members left: $(pgrep -g "$pid" | wc -l)"
  pkill -KILL -g "$pid" 2>/dev/null
}

probe plain
probe goto "goto $page"
probe click "goto $page" "click #b"
probe type "goto $page" "type #i hello"
probe newtab "newtab about:blank"
