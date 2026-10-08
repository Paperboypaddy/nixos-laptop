#!/bin/sh
REPO="$HOME/nixos-config"
git -C "$REPO" fetch --quiet 2>/dev/null
n=$(git -C "$REPO" rev-list --count "HEAD..@{u}")
[ "$n" -gt 0 ] || { notify-send "Config is up to date"; exit 0; }
choice=$(printf 'Update now\nApply at next reboot\nCancel\n' | wmenu -p "$n new config change(s):")
case "$choice" in
  "Update now") mode=switch ;;
  "Apply at next reboot") mode=boot ;;
  *) exit 0 ;;
esac
foot -e sh -c "cd '$REPO' && git pull --ff-only && sudo nixos-rebuild $mode; echo; echo 'Finished. Press Enter to close.'; read x"
