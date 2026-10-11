#!/bin/sh
# Waybar helper: prints JSON that shows an icon when updates are waiting.
REPO="$HOME/nixos-config"
n=$(git -C "$REPO" rev-list --count "HEAD..@{u}" 2>/dev/null)
n=${n:-0}
if [ "$n" -gt 0 ]; then
  subj=$(git -C "$REPO" log -1 --format=%s "@{u}" | tr -d '"\\')
  printf '{"text":"","alt":"pending","tooltip":"%s update(s) waiting: %s"}\n' "$n" "$subj"
else
  printf '{"text":"","alt":"none"}\n'
fi
