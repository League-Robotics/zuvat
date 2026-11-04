# zuvat

Programs and the SD-card image for zuvat: a Nezha robot with a
Raspberry Pi 3 (talking to the micro:bit over USB, like the Pi Zero nodes)
and a USB webcam.

## The image

`make image` builds `build/zuvat-YYYYMMDD.img.xz`: Raspberry Pi OS Lite
64-bit (trixie, 2026-10-06), headless, with:

| What | Where |
|---|---|
| mbtools (mbregistry, mbdeploy, mbserial, mbrelay) as the `mbtools` .deb; `mbregistry.service` enabled | `/usr/lib/mbtools`, `/usr/bin/mb*` |
| `mbtools-update [VERSION]`: upgrade mbtools from its GitHub release (default latest; does nothing if already current) | `/usr/local/sbin` |
| Vision venv: OpenCV-contrib (headless; AprilTag 36h11 and ArUco via `cv2.aruco`), numpy, scipy, aprilcam, plus `import mbtools` | `/opt/vision`, on `PATH` for login shells; owned by `jtl` |
| USB camera tools: `v4l2-ctl`, `ffmpeg`, `fswebcam`, `ustreamer` | |
| CSI camera tools: `rpicam-*`, `cam` | |
| Python 3.13 with venv/pip/dev headers, build-essential, `uv` | |
| git, tmux, screen, htop, vim, jq, rsync, picocom, i2c-tools, usbutils, avahi | |

Locale en_US.UTF-8, timezone America/Los_Angeles, US keyboard and Wi-Fi
region. SSH on, keys only.

The image has **no user, password or Wi-Fi key** in it, so it can be shared.
Those go onto the card's boot partition as a cloud-init seed when it is
flashed. The same image works for any of these robots; only the seed
changes.

What a card was built from: `/etc/zuvat-image/` (`release`, the full package
list, the vision venv's `pip freeze`). The same files are saved next to the
image as `build/zuvat-YYYYMMDD.manifest/`.

### Build

Needs Docker on an arm64 Mac (OrbStack) and `uv`. The aprilcam wheel is
built from `../aprilcam` (`APRILCAM_SRC=` to change). Pin mbtools with
`MBTOOLS_VERSION=0.20261024.2 make image`.

    make image

### Flash a card

    make flash DISK=/dev/diskN                       # zuvat, DHCP
    make flash DISK=/dev/diskN ARGS="-n vevov -i 192.168.4.x"

`diskutil list external` finds the card. The script asks you to type the
device back before it erases it, and sudo asks for your password for `dd`.
The seed gives `jtl` Eric's keys from
`busboom-home-network/config/keys/eric.pub`, passwordless sudo, the
`PI_JTL_PASSWORD` console password, and `Robot_Garage` Wi-Fi. Both secrets
are read from that repo's dotconfig `.env`. To seed a card that was flashed
some other way (Raspberry Pi Imager "Use custom", Etcher), mount its boot
partition and run `image/seed.sh /Volumes/bootfs`.

First boot grows the filesystem to the card, makes new SSH host keys,
creates `jtl` and joins Wi-Fi. Give it about 3 minutes, then `make ssh`
(`zuvat.local`).

### After first boot

- Reserve its address on sajak (MAC from `ip link show wlan0`), as for jarl:
  `services/dnsmasq` in busboom-home-network, and add a `hosts/zuvat/` record.
- Upgrade mbtools: `sudo mbtools-update`.
- Webcam check: `v4l2-ctl --list-devices`;
  `ustreamer --device /dev/video0 --host 0.0.0.0 --port 8080` for a browser view.
