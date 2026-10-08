#!/bin/sh
while true; do
  b=/sys/class/power_supply/BAT0
  echo "BAT $(cat $b/capacity)% ($(cat $b/status)) | $(date '+%a %b %d %H:%M')"
  sleep 30
done
