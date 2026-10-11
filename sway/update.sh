#!/usr/bin/env bash
REPO="$HOME/nixos-config"
SNAP="$HOME/.cache/session-snapshot"
cd "$REPO" || exit 1
pause() { read -rp "Press Enter to close. " _; }

git fetch --quiet || { echo "Can't reach GitHub."; pause; exit 1; }
n=$(git rev-list --count HEAD..'@{u}')
[ "$n" -gt 0 ] || { echo "Config is up to date."; sleep 2; exit 0; }
echo "$n new change(s):"
git log --format='  %h %s' HEAD..'@{u}'
read -rp $'\nApply now? [y/N] ' a
[ "$a" = y ] || exit 0

old=$(git rev-parse HEAD)
git pull --ff-only || { echo "Pull failed (unpushed local edits?)."; pause; exit 1; }

sudo tlp ac >/dev/null 2>&1   # lift the battery CPU cap during the rebuild
LOG=$(mktemp)
set -o pipefail
if ! sudo nixos-rebuild switch 2>&1 | tee "$LOG"; then
  sudo tlp start >/dev/null 2>&1
  echo; echo "Rebuild failed. The running system is unchanged."
  read -rp "Revert the pull? [y/N] " r
  [ "$r" = y ] && git reset --keep "$old"
  exit 1
fi
sudo tlp start >/dev/null 2>&1

reboot=0; relog=0; reload=0
for f in initrd kernel kernel-modules; do
  [ "$(readlink -f /run/booted-system/$f)" = "$(readlink -f /run/current-system/$f)" ] || reboot=1
done
cmp -s /run/booted-system/kernel-params /run/current-system/kernel-params || reboot=1
grep 'NOT restarting' "$LOG" | grep -Eq 'greetd|display-manager' && reboot=1

now=$(printf '%s\n' "$(readlink -f /run/current-system/sw/bin/sway)" "$(readlink -f /etc/set-environment)")
[ -f "$SNAP" ] && [ "$now" != "$(cat "$SNAP")" ] && relog=1
[ "$(id -Gn | tr ' ' '\n' | sort)" != "$(id -Gn "$USER" | tr ' ' '\n' | sort)" ] && relog=1
git diff --name-only "$old" HEAD | grep -q '^sway/' && reload=1
git diff --name-only "$old" HEAD | grep -q '^waybar/' && pkill -SIGUSR2 waybar

echo
if [ $reboot = 1 ]; then
  echo "Reboot needed (kernel, boot, or login screen changed)."
  read -rp "Reboot now? [y/N] " r
  [ "$r" = y ] && exec systemctl reboot
fi
if [ $relog = 1 ]; then
  echo "Relog needed (Sway, session environment, or groups changed)."
  read -rp "Log out of Sway now? [y/N] " r
  [ "$r" = y ] && exec swaymsg exit
fi
if [ $reload = 1 ] && [ $relog = 0 ]; then
  read -rp "Sway config changed. Reload now? [Y/n] " r
  [ "$r" = n ] || swaymsg reload
fi
echo "Done."; sleep 3
