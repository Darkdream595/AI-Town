#!/usr/bin/env bash
# page-eval.sh <session> <js-file>
# Windows-safe kimi-webbridge evaluate call: wraps the JS from <js-file> into a
# JSON request body (via python, no shell-escaping issues with non-ASCII),
# POSTs it with curl.exe, prints the daemon response.
# The JS runs in the current tab of <session>; use an IIFE and return JSON.stringify(...).
set -u
SESSION="$1"
JSFILE="$2"
TMP="$(mktemp --suffix=.json)"

python - "$JSFILE" "$SESSION" > "$TMP" <<'EOF'
import json, sys
code = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({"action": "evaluate", "args": {"code": code}, "session": sys.argv[2]}))
EOF

curl.exe -s -X POST http://127.0.0.1:10086/command \
  -H "Content-Type: application/json" \
  --data-binary "@$(cygpath -w "$TMP")"
rc=$?
rm -f "$TMP"
exit $rc
