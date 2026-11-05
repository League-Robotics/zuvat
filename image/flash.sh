#!/usr/bin/env bash
# Write a zuvat image to an SD card (macOS), then seed it with image/seed.sh.
#
#   image/flash.sh [-d /dev/diskN] [-m IMAGE.img.xz] [seed.sh options]
#
# Without -d, lists the external disks that could be SD cards and asks
# which one. IMAGE defaults to the newest build/zuvat-*.img.xz.
set -euo pipefail
cd "$(dirname "$0")/.."

MAX_BYTES=130000000000
DEVICE=""
IMAGE=""
SEED_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        -d) DEVICE="$2"; shift 2 ;;
        -m) IMAGE="$2"; shift 2 ;;
        *) SEED_ARGS+=("$1"); shift ;;
    esac
done

[ -n "$IMAGE" ] || IMAGE="$(ls -t build/zuvat-*.img.xz 2>/dev/null | head -1)"
[ -f "$IMAGE" ] || { echo "no image (run make image, or pass -m)" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running (open OrbStack)" >&2; exit 1; }
docker build -q -t zuvat-imager image >/dev/null

disk_bytes() { diskutil info "$1" | sed -n 's/.*(\([0-9]*\) Bytes).*/\1/p' | head -1; }
disk_field() { diskutil info "$1" | awk -F': *' -v k="$2" '$1 ~ k {print $2; exit}'; }
disk_gb() { awk -v b="$(disk_bytes "$1")" 'BEGIN { printf "%.1f GB", b / 1e9 }'; }
disk_volumes() {
    diskutil list "$1" | awk 'NR > 2 && $NF ~ /s[0-9]+$/ { n = ""; for (i = 3; i <= NF - 3; i++) n = n (n ? " " : "") $i; if (n) printf "%s%s", (c++ ? ", " : ""), n }'
}

if [ -z "$DEVICE" ]; then
    CANDIDATES=()
    for d in $(diskutil list external physical | grep -oE '^/dev/disk[0-9]+'); do
        b="$(disk_bytes "$d")"
        [ "${b:-0}" -gt 0 ] && [ "$b" -le "$MAX_BYTES" ] && CANDIDATES+=("$d")
    done
    [ ${#CANDIDATES[@]} -gt 0 ] || { echo "no SD card found (external disks up to 128 GB)" >&2; exit 1; }
    echo "SD cards:"
    i=1
    for d in "${CANDIDATES[@]}"; do
        printf "  %d) %-12s %-9s %-24s %s\n" "$i" "$d" "$(disk_gb "$d")" "$(disk_field "$d" "Device / Media Name")" "$(disk_volumes "$d")"
        i=$((i + 1))
    done
    read -r -p "Which card? [1-${#CANDIDATES[@]}] " PICK
    case "$PICK" in ''|*[!0-9]*) echo "no card chosen" >&2; exit 1 ;; esac
    [ "$PICK" -ge 1 ] && [ "$PICK" -le ${#CANDIDATES[@]} ] || { echo "no card chosen" >&2; exit 1; }
    DEVICE="${CANDIDATES[$((PICK - 1))]}"
fi

[ "$(disk_field "$DEVICE" "Device Location")" = External ] || { echo "$DEVICE is not an external disk" >&2; exit 1; }
[ "$(disk_bytes "$DEVICE")" -le "$MAX_BYTES" ] || { echo "$DEVICE is larger than 128 GB; refusing" >&2; exit 1; }

SEED_DIR="$(mktemp -d)"
trap 'rm -rf "$SEED_DIR"' EXIT
image/seed.sh "$SEED_DIR" ${SEED_ARGS[@]+"${SEED_ARGS[@]}"}

echo
echo "  card : $DEVICE  $(disk_gb "$DEVICE")  $(disk_field "$DEVICE" "Device / Media Name")  [$(disk_volumes "$DEVICE")]"
echo "  image: $(basename "$IMAGE")"
echo "  EVERYTHING ON $DEVICE WILL BE ERASED."
read -r -p "Flash it? [y/N] " OK
case "$OK" in y|Y|yes|YES) ;; *) echo "cancelled" >&2; exit 1 ;; esac

echo "sudo password for dd:"
sudo -v

START=$SECONDS
echo "[1/4] unmounting $DEVICE"
diskutil unmountDisk "$DEVICE"

echo "[2/4] writing $(basename "$IMAGE")"
IMG_DIR="$(cd "$(dirname "$IMAGE")" && pwd)"
docker run --rm -v "$IMG_DIR:/img:ro" -e IMG="/img/$(basename "$IMAGE")" zuvat-imager sh -c '
    SIZE=$(xz --robot --list "$IMG" | awk "\$1 == \"totals\" {print \$5}")
    xz -dc -T0 "$IMG" | pv -f -w 78 -s "$SIZE"' \
    | sudo dd of="${DEVICE/disk/rdisk}" bs=4m 2>/dev/null
sync

echo "[3/4] writing first-boot files"
diskutil mountDisk "$DEVICE" >/dev/null || true
BOOT=""
for _ in $(seq 1 15); do
    BOOT="$(disk_field "${DEVICE}s1" "Mount Point")"
    [ -n "$BOOT" ] && [ -f "$BOOT/config.txt" ] && break
    BOOT=""
    sleep 1
done
[ -n "$BOOT" ] || { echo "boot partition ${DEVICE}s1 did not mount" >&2; exit 1; }

cp "$SEED_DIR"/user-data "$SEED_DIR"/network-config "$SEED_DIR"/meta-data "$BOOT"/
sync
echo "[4/4] ejecting"
diskutil eject "$DEVICE"
echo "done in $(( (SECONDS - START) / 60 ))m$(( (SECONDS - START) % 60 ))s: put the card in the Pi and power it on; first boot takes a few minutes."
