# nixos-laptop

NixOS configuration for a Dell Latitude 5420 (Intel i5, NVMe), dual-booted
alongside Windows 11. It's tuned for a terminal-and-browser workflow with as
little battery drain as possible.

## Layout

| Path | Purpose |
|------|---------|
| `configuration.nix` | Main system configuration |
| `hardware-configuration.nix` | Generated for this machine. Regenerate on different hardware |
| `sway/` | Sway config and helper scripts, symlinked to `~/.config/sway` |
| `sway/config` | Sway config (keybindings, outputs, input settings, bar) |
| `sway/status.sh` | Top-bar status: battery percentage and state, plus the clock |
| `sway/update-check.sh` | Background notifier for new config commits |
| `sway/update.sh` | Interactive updater (Super+Shift+U) |

`/etc/nixos` is a symlink to this repo's clone (`~/nixos-config`), so plain
`sudo nixos-rebuild switch` builds from it.

## What's configured

- **Boot:** GRUB on EFI, reusing the existing Windows EFI partition at
  `/boot/efi`. NixOS lives on its own ext4 partition. Windows is untouched.
- **Desktop:** Sway, started through greetd/tuigreet. foot terminal, wmenu
  launcher, mako notifications, UI scale 1.12 on the 1080p panel.
- **Power:** TLP plus thermald. On battery: `powersave` governor, turbo off,
  CPU capped to about 700 MHz. On AC: full speed.
- **Browser:** LibreWolf (uBlock Origin ships with it). Per-user tweaks such as
  keeping cookies and disabling `privacy.resistFingerprinting` live in
  `~/.librewolf/librewolf.overrides.cfg`, which is not tracked here.
- **Auth:** Howdy face unlock using the IR camera, set to `sufficient`, so the
  password always works as a fallback.
- **Shell:** fish.
- **Passwords:** Bitwarden desktop, set up for polkit-based biometric unlock.
- **Remote access:** OpenSSH enabled for use on the LAN.

## Keybindings (Sway, `$mod` = Super)

| Keys | Action |
|------|--------|
| `$mod+Enter` | Terminal |
| `$mod+D` | Launcher |
| `$mod+Shift+B` | Open LibreWolf |
| `$mod+Shift+U` | Check for and apply config updates |
| `$mod+Shift+C` | Reload Sway config |
| `$mod+Shift+Q` | Close window |

## Day to day

```sh
cd ~/nixos-config
# edit configuration.nix or sway/*
sudo nixos-rebuild switch
git add -A && git commit -m "What changed" && git push
```

Rollback: pick an earlier generation in the GRUB menu, or run
`sudo nixos-rebuild switch --rollback`.

## Updates

Nothing is ever applied automatically.

1. `sway/update-check.sh` starts with Sway. Two minutes after login, then every
   30 minutes, it runs `git fetch`. If it's offline, the fetch fails and the
   round is skipped.
2. If the remote has new commits, a notification appears once per new commit.
3. When ready, press **Super+Shift+U**. A terminal lists the pending commits and
   asks for confirmation.
4. On "yes", `update.sh` pulls (fast-forward only) and runs
   `sudo nixos-rebuild switch`. It lifts the battery CPU cap during the rebuild.
   If the rebuild fails, the running system is unchanged and the script offers
   to revert the pull.
5. Afterwards it works out what else is needed and asks:

| Need | Triggered by |
|------|--------------|
| **Reboot** | New kernel, initrd, kernel modules or kernel params, or the login manager was not restarted |
| **Relog** | The Sway package or session environment changed since login, or group membership changed |
| **Reload** | Only Sway config files in this repo changed |
| **Nothing** | Everything else (services restart themselves on `switch`) |

These checks are heuristics. When in doubt, reboot.

## Planned

- Convert to flakes with a pinned `flake.lock`, so CI and the laptop build the
  same system.
- GitHub Actions: evaluate and build on every push, and advance a `stable`
  branch only when the build is green. The laptop would track `stable`.
- A commit trailer convention for post-update actions:

  ```
  Post-update: reboot | relog | reload | none
  ```

  CI would compare builds and fail if the trailer claims less than the diff
  needs. `update.sh` would read the trailers for the pulled range and take the
  most severe action.
- AI agents propose changes through pull requests only.

## Fresh install notes

- Partitions: the Windows EFI partition is reused and mounted at `/boot/efi`
  (not formatted). A new ext4 root is labelled `nixos`.
- Bootloader: GRUB (`efiSupport`, `device = "nodev"`) rather than systemd-boot,
  because the Windows EFI partition is only 100 MB.
- Clone this repo to `~/nixos-config`, replace the generated config with it, and
  point `/etc/nixos` at the clone:

  ```sh
  sudo mv /etc/nixos /etc/nixos.bak
  sudo ln -s ~/nixos-config /etc/nixos
  ln -s ~/nixos-config/sway ~/.config/sway
  ```

- Regenerate `hardware-configuration.nix` with `nixos-generate-config` if the
  hardware differs.

## Known issues

- GRUB's os-prober doesn't list Windows. Boot it from the firmware menu (F12),
  or add a manual `boot.loader.grub.extraEntries` chainload entry.
- Bitwarden's LibreWolf extension isn't linked to the desktop app for
  biometric unlock yet.

## Security

- Keep the repo private, with 2FA on the GitHub account.
- Never commit passwords, tokens, or `initialPassword`. WiFi credentials and
  face models are stored outside this repo.
- Anything that lands on the branch the laptop tracks runs as root on the next
  update, so review changes (especially agent-written ones) before merging.
