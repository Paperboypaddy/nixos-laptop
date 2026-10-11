# Edit this configuration file to define what should be installed on
# your system. Help is available in the configuration.nix(5) man page, on
# https://search.nixos.org/options and in the NixOS manual (`nixos-help`).

{ config, lib, pkgs, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  # Use the systemd-boot EFI boot loader.
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

  # networking.hostName = "nixos"; # Define your hostname.

  # Configure network connections interactively with nmcli or nmtui.
  networking.networkmanager.enable = true;

  # Users
  users.users.paper = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "video" "wireshark" ];
    packages = with pkgs; [
      tree
    ];
  };

  # desktop
  programs.sway = {
    enable = true;
    wrapperFeatures.gtk = true;
  };
  services.greetd = {
    enable = true;
    settings.default_session.command =
      "${pkgs.greetd.tuigreet}/bin/tuigreet --cmd sway";
  };
  fonts.packages = [ pkgs.dejavu_fonts ];
  programs.fish.enable = true;
  users.users.paper.shell = pkgs.fish;

  environment.systemPackages = with pkgs; [
    # desktop and apps
    foot wmenu brightnessctl powertop librewolf kitty
    mako libnotify bitwarden-desktop polkit_gnome
    # config and dev
    git gh wireguard-tools
    # network tools
    traceroute nmap tcpdump iperf3 bind whois ethtool arp-scan
  ];

  programs.mtr.enable = true;
  programs.wireshark = {
    enable = true;
    package = pkgs.wireshark-cli;   # tshark only, no Qt GUI
  };

  security.polkit.enable =true;
  services.gnome.gnome-keyring.enable = true;
  security.pam.services.greetd.enableGnomeKeyring = true;
  environment.pathsToLink = [ "/libexec" ];


  #howdy face unlock
  services.howdy = {
    enable = true;
    control = "sufficient";   # face OR password
    settings = {
      core.no_confirmation = true;
      video.device_path = "/dev/video2";
    };
  };

  #wireguard config
  networking.wg-quick.interfaces.homelab = {
    configFile = "/etc/wireguard/homelab.conf";   # lives outside the repo
    autostart = true;                            # connect only when needed
  };

  # power
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

  # keep it lean
  services.printing.enable = false;
  services.avahi.enable = false;
  documentation.enable = false;

  # System Version
  system.stateVersion = "26.05";

}

