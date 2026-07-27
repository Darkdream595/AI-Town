#!/usr/bin/env bash
# wait-and-move.sh <target-path> [downloads-dir] [timeout-seconds]
# Poll for character-spritesheet.png in the user's Downloads folder (a GUID .tmp
# file may sit at a frozen size first — that is normal, it finalizes on its own),
# then move it to <target-path>. Git Bash (Windows) compatible.
set -u
TARGET="$1"
DL="${2:-$USERPROFILE/Downloads}"
TIMEOUT="${3:-120}"
NAME="character-spritesheet.png"

elapsed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
  if [ -f "$DL/$NAME" ]; then
    mv "$DL/$NAME" "$TARGET" && echo "MOVED -> $TARGET" && exit 0
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done
echo "TIMEOUT: $NAME never finalized in $DL" >&2
ls -lt "$DL" | head -5 >&2
exit 1
