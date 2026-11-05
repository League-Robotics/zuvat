#!/usr/bin/env bash
# Write the cloud-init seed (user-data, network-config, meta-data) onto a
# flashed card's boot partition, or into any directory to preview it.
#
#   image/seed.sh BOOTDIR [-n NAME] [-i IP] [--no-password]
#
#   -n NAME        hostname (default zuvat)
#   -i IP          static wlan0 address on Robot_Garage (default: DHCP)
#   --no-password  no console password for jtl (SSH keys only)
#
# Secrets come from the environment (ROBOT_GARAGE_WIFI_PASSWORD,
# PI_JTL_PASSWORD) or from the home-network repo's dotconfig .env.
# Keys for jtl: $HOMENET/config/keys/eric.pub.
set -euo pipefail

HOMENET="${HOMENET:-/Volumes/Proj/proj/home-projects/busboom-home-network}"
WIFI_SSID=Robot_Garage
NET_PREFIX=23
NET_GW=192.168.4.1

BOOT=""
NAME=zuvat
IP=""
WITH_PASSWORD=1
while [ $# -gt 0 ]; do
    case "$1" in
        -n) NAME="$2"; shift 2 ;;
        -i) IP="$2"; shift 2 ;;
        --no-password) WITH_PASSWORD=0; shift ;;
        -*) echo "unknown option $1" >&2; exit 2 ;;
        *) BOOT="$1"; shift ;;
    esac
done
[ -n "$BOOT" ] && [ -d "$BOOT" ] || { echo "usage: seed.sh BOOTDIR [-n NAME] [-i IP] [--no-password]" >&2; exit 2; }
echo "$NAME" | grep -qE '^[a-z][a-z0-9-]*$' || { echo "bad hostname: $NAME" >&2; exit 2; }

env_value() {
    local raw
    raw="$(grep -E "^(export[[:space:]]+)?$1=" "$HOMENET/.env" 2>/dev/null | tail -1)" || return 0
    raw="${raw#*=}"
    case "$raw" in
        \'*\') raw="${raw:1:${#raw}-2}" ;;
        \"*\") raw="${raw:1:${#raw}-2}" ;;
    esac
    printf '%s' "$raw"
}

yaml_quote() {
    local s="${1//\\/\\\\}"
    printf '"%s"' "${s//\"/\\\"}"
}

PSK="${ROBOT_GARAGE_WIFI_PASSWORD:-$(env_value ROBOT_GARAGE_WIFI_PASSWORD)}"
[ -n "$PSK" ] || { echo "ROBOT_GARAGE_WIFI_PASSWORD not set and not in $HOMENET/.env" >&2; exit 1; }
KEYS="$HOMENET/config/keys/eric.pub"
[ -s "$KEYS" ] || { echo "no SSH keys at $KEYS" >&2; exit 1; }

HASH=""
if [ "$WITH_PASSWORD" = 1 ]; then
    PW="${PI_JTL_PASSWORD:-$(env_value PI_JTL_PASSWORD)}"
    [ -n "$PW" ] || { echo "PI_JTL_PASSWORD not set and not in $HOMENET/.env (or pass --no-password)" >&2; exit 1; }
    HASH="$(printf '%s' "$PW" | docker run --rm -i zuvat-imager openssl passwd -6 -stdin)"
fi

if [ -n "$IP" ]; then
    WLAN_ADDR="      dhcp4: false
      addresses: [$IP/$NET_PREFIX]
      routes:
        - to: default
          via: $NET_GW
      nameservers:
        addresses: [$NET_GW]"
else
    WLAN_ADDR="      dhcp4: true"
fi

cat > "$BOOT/network-config" <<EOF
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    eth0:
      dhcp4: true
      optional: true
  wifis:
    wlan0:
$WLAN_ADDR
      optional: true
      regulatory-domain: US
      access-points:
        $(yaml_quote "$WIFI_SSID"):
          password: $(yaml_quote "$PSK")
EOF

cat > "$BOOT/meta-data" <<EOF
dsmode: local
instance-id: $NAME-$(date +%Y%m%d%H%M%S)
EOF

{
    echo "#cloud-config"
    echo "hostname: $NAME"
    echo "manage_etc_hosts: true"
    echo "ssh_pwauth: false"
    echo "users:"
    echo "  - name: jtl"
    echo "    gecos: jtl"
    echo "    shell: /bin/bash"
    echo "    groups: [adm, dialout, plugdev, video, render, gpio, i2c, spi, input, netdev, sudo, users]"
    echo "    sudo: \"ALL=(ALL) NOPASSWD:ALL\""
    if [ -n "$HASH" ]; then
        echo "    lock_passwd: false"
        echo "    passwd: $(yaml_quote "$HASH")"
    else
        echo "    lock_passwd: true"
    fi
    echo "    ssh_authorized_keys:"
    grep -E '^(ssh|ecdsa)-' "$KEYS" | while read -r key; do echo "      - $(yaml_quote "$key")"; done
    echo "runcmd:"
    echo "  - [chown, -R, \"jtl:jtl\", /opt/vision]"
    echo "  - [sync]"
} > "$BOOT/user-data"

echo "seeded $BOOT: hostname $NAME, wlan0 ${IP:-DHCP} on $WIFI_SSID, user jtl$([ -n "$HASH" ] && echo ' (password + keys)' || echo ' (keys only)')"
