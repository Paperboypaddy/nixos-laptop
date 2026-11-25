{ config, lib, pkgs, ... }:

let
  # This helper can only toggle the homelab WireGuard systemd unit.
  wgToggle = pkgs.writeShellScriptBin "wg-toggle" ''
    unit="wg-quick-homelab.service"
    if ${pkgs.systemd}/bin/systemctl is-active --quiet "$unit"; then
      exec ${pkgs.systemd}/bin/systemctl stop "$unit"
    else
      exec ${pkgs.systemd}/bin/systemctl start "$unit"
    fi
  '';

  # Waybar polls this helper for the tunnel's current state.
  wgStatus = pkgs.writeShellScriptBin "wg-status" ''
    if ${pkgs.systemd}/bin/systemctl is-active --quiet wg-quick-homelab.service; then
      printf '%s\n' '{"text":"","class":"connected","tooltip":"WireGuard: connected"}'
    else
      printf '%s\n' '{"text":"","class":"disconnected","tooltip":"WireGuard: disconnected"}'
    fi
  '';
in
{
  imports = [ ./hardware-configuration.nix ];

  # GRUB EFI bootloader, sharing the existing EFI system partition.
  boot.loader.efi.canTouchEfiVariables = true;
  boot.loader.efi.efiSysMountPoint = "/boot/efi";
  boot.loader.grub = {
    enable = true;
    efiSupport = true;
    device = "nodev";
    useOSProber = true;
  };
  hardware.enableRedistributableFirmware = true;
  services.openssh.enable = true;

  networking.networkmanager.enable = true;

  users.users.paper = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "video" "wireshark" ];
    packages = with pkgs; [ tree ];
  };

  programs.sway = {
    enable = true;
    wrapperFeatures.gtk = true;
  };
  services.greetd = {
    enable = true;
    settings.default_session.command =
      "${pkgs.tuigreet}/bin/tuigreet --cmd sway";
  };
  fonts.packages = [ pkgs.dejavu_fonts pkgs.font-awesome ];
  programs.fish.enable = true;
  users.users.paper.shell = pkgs.fish;

  environment.systemPackages = with pkgs; [
    foot wmenu brightnessctl powertop librewolf kitty
    mako libnotify bitwarden-desktop polkit_gnome
    waybar networkmanagerapplet adwaita-icon-theme
    git gh wireguard-tools
    traceroute nmap tcpdump iperf3 bind whois ethtool arp-scan
    (stdenvNoCC.mkDerivation {
      pname = "config-update";
      version = "1.0";
      dontUnpack = true;
      nativeBuildInputs = [ wrapGAppsHook3 gobject-introspection ];
      buildInputs = [ gtk3 ];
      installPhase = ''
        mkdir -p "$out/bin"
        cat > "$out/bin/config-update" <<'EOF'
#!${pkgs.runtimeShell}
exec ${pkgs.python3.withPackages (ps: [ ps.pygobject3 ])}/bin/python3 ${./sway/update-ui.py} "$@"
EOF
        chmod +x "$out/bin/config-update"
      '';
    })
    (writeShellScriptBin "config-update-check" (builtins.readFile ./sway/update-check.sh))
    (writeShellScriptBin "config-update-status" (builtins.readFile ./sway/update-status.sh))
    (writeShellScriptBin "sway-session" ''
      exec ${pkgs.python3}/bin/python3 ${./sway/session.py} "$@"
    '')
    wgToggle
    wgStatus
  ];

  # Permit only this fixed helper to run without a password.
  security.sudo.extraRules = [{
    users = [ "paper" ];
    commands = [{
      command = "${wgToggle}/bin/wg-toggle";
      options = [ "NOPASSWD" ];
    }];
  }];

  environment.etc."sway/config".source = ./sway/config;
  environment.etc."xdg/waybar/config.jsonc".source = ./waybar/config.jsonc;
  environment.etc."xdg/waybar/style.css".source = ./waybar/style.css;

  systemd.tmpfiles.rules = [
    "d /home/paper/.config/librewolf 0700 paper users -"
    "d /home/paper/.config/librewolf/librewolf 0700 paper users -"
    "L+ /home/paper/.config/librewolf/librewolf/librewolf.overrides.cfg - - - - ${./librewolf.overrides.cfg}"
    "d /home/paper/.librewolf 0700 paper users -"
    "L+ /home/paper/.librewolf/librewolf.overrides.cfg - - - - ${./librewolf.overrides.cfg}"
  ];

  programs.mtr.enable = true;
  programs.wireshark = {
    enable = true;
    package = pkgs.wireshark-cli;
  };

  # Graphical administrative prompts use password authentication, not Howdy.
  security.pam.services.polkit-1.rules.auth.howdy.enable = lib.mkForce false;
  security.polkit.enable = true;
  security.polkit.extraConfig = ''
    polkit.addAdminRule(function(action, subject) {
      if (action.id == "org.freedesktop.policykit.exec" &&
          subject.user == "paper" && subject.local && subject.active &&
          action.lookup("program") == "/run/current-system/sw/bin/nixos-rebuild") {
        return ["unix-user:paper"];
      }
    });
  '';
  services.gnome.gnome-keyring.enable = true;
  security.pam.services.greetd.enableGnomeKeyring = true;
  environment.pathsToLink = [ "/libexec" ];

  services.howdy = {
    enable = true;
    control = "sufficient";
    settings = {
      core.no_confirmation = true;
      video.device_path = "/dev/video2";
    };
  };

  # The private tunnel config stays outside this repository.
  networking.wg-quick.interfaces.homelab = {
    configFile = "/etc/wireguard/homelab.conf";
    autostart = true;
  };

  boot.kernel.sysctl = {
    "net.ipv4.conf.all.arp_ignore" = 1;
    "net.ipv4.conf.all.arp_announce" = 2;
  };

  networking.firewall.checkReversePath = "loose";
  networking.networkmanager.dispatcherScripts = [{
    type = "basic";
    source = pkgs.writeShellScript "wifi-off-when-same-lan" ''
      nmcli=${pkgs.networkmanager}/bin/nmcli
      flag=/run/wifi-off-by-eth
      [ "$($nmcli -g GENERAL.TYPE device show "$1")" = ethernet ] || exit 0
      case "$2" in
        up)
          wifi_dev=$($nmcli -t -f DEVICE,TYPE device | ${pkgs.gawk}/bin/awk -F: '$2=="wifi"{print $1; exit}')
          eth_gw=$($nmcli -g IP4.GATEWAY device show "$1")
          wifi_gw=$($nmcli -g IP4.GATEWAY device show "$wifi_dev")
          if [ -n "$eth_gw" ] && [ "$eth_gw" = "$wifi_gw" ]; then
            touch "$flag"; $nmcli radio wifi off
          fi ;;
        down)
          [ -e "$flag" ] && rm "$flag" && $nmcli radio wifi on ;;
      esac
    '';
  }];

  services.power-profiles-daemon.enable = false;
  services.thermald.enable = true;
  services.tlp = {
    enable = true;
    settings = {
      CPU_SCALING_GOVERNOR_ON_BAT = "powersave";
      CPU_ENERGY_PERF_POLICY_ON_BAT = "power";
      CPU_BOOST_ON_BAT = 0;
      CPU_SCALING_MIN_FREQ_ON_BAT = 400000;
      CPU_SCALING_MAX_FREQ_ON_BAT = 700000;
      CPU_SCALING_GOVERNOR_ON_AC = "powersave";
      CPU_ENERGY_PERF_POLICY_ON_AC = "balance_performance";
      CPU_BOOST_ON_AC = 1;
      PCIE_ASPM_ON_BAT = "powersupersave";
      USB_AUTOSUSPEND = 1;
      RUNTIME_PM_ON_BAT = "auto";
    };
  };
  networking.networkmanager.wifi.powersave = true;

  services.printing.enable = false;
  services.avahi.enable = false;
  documentation.enable = false;

  system.stateVersion = "26.05";
}
