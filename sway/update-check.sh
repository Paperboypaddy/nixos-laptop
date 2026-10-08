#!/bin/sh
REPO="$HOME/nixos-config"
STATE="$HOME/.cache/config-update-notified"
mkdir -p "$HOME/.cache"
on_ac() { cat /sys/class/power_supply/A*/online 2>/dev/null | grep -q 1; }
sleep 120
while true; do
  if on_ac && timeout 30 git -C "$REPO" fetch --quiet 2>/dev/null; then
    new=$(git -C "$REPO" rev-parse "@{u}")
    n=$(git -C "$REPO" rev-list --count "HEAD..@{u}")
    if [ "$n" -gt 0 ] && [ "$new" != "$(cat "$STATE" 2>/dev/null)" ]; then
      subj=$(git -C "$REPO" log -1 --format=%s "@{u}")
      notify-send "Config update available" "$n new: $subj
Press Super+Shift+U when you're ready."
      echo "$new" > "$STATE"
    fi
  fi
  sleep 1800
done
