#!/bin/bash
# Runs in the privileged zuvat-imager container with the repo at /repo.
# Usage: inside.sh BASE.img.xz OUT.img  (paths relative to /repo)
set -euo pipefail

BASE="/repo/$1"
OUT="/repo/$2"
GROW="${GROW:-3G}"
IMG=/work/image.img
MNT=/mnt/root
LOOPS=()

cleanup() {
    umount -R "$MNT" 2>/dev/null || true
    for l in "${LOOPS[@]}"; do losetup -d "$l" 2>/dev/null || true; done
}
trap cleanup EXIT

attach() {
    local start sectors
    read -r start sectors < <(partx -g -n "$1" -o START,SECTORS "$IMG")
    losetup -f --show -o $((start * 512)) --sizelimit $((sectors * 512)) "$IMG"
}

mkdir -p /work "$MNT"
echo "==> unpacking $(basename "$BASE")"
xz -dc -T0 "$BASE" > "$IMG"
truncate -s "+$GROW" "$IMG"
echo ", +" | sfdisk --no-reread --no-tell-kernel -N 2 "$IMG"

ROOT_DEV="$(attach 2)"; LOOPS+=("$ROOT_DEV")
BOOT_DEV="$(attach 1)"; LOOPS+=("$BOOT_DEV")
e2fsck -pf "$ROOT_DEV"
resize2fs "$ROOT_DEV"

mount "$ROOT_DEV" "$MNT"
mount "$BOOT_DEV" "$MNT/boot/firmware"
mount -t proc proc "$MNT/proc"
mount -t sysfs sys "$MNT/sys"
mount --bind /dev "$MNT/dev"
mount --bind /dev/pts "$MNT/dev/pts"

mv "$MNT/etc/resolv.conf" "$MNT/etc/resolv.conf.zuvat"
cp /etc/resolv.conf "$MNT/etc/resolv.conf"

mkdir -p "$MNT/tmp/zuvat"
cp /repo/image/customize.sh /repo/image/packages.txt /repo/image/requirements-vision.txt \
   /repo/build/wheels/aprilcam-*.whl "$MNT/tmp/zuvat/"

echo "==> customizing"
chroot "$MNT" env BASE_IMAGE="$(basename "$BASE")" MBTOOLS_VERSION="${MBTOOLS_VERSION:-latest}" \
    /bin/bash /tmp/zuvat/customize.sh

rm -rf "$MNT/tmp/zuvat"
mv -f "$MNT/etc/resolv.conf.zuvat" "$MNT/etc/resolv.conf"
rm -rf "${OUT%.img}.manifest"
cp -r "$MNT/etc/zuvat-image" "${OUT%.img}.manifest"

umount "$MNT/dev/pts" "$MNT/dev" "$MNT/sys" "$MNT/proc"
echo "==> zeroing free space"
fstrim -v "$MNT/boot/firmware" || true
if ! fstrim -v "$MNT"; then
    dd if=/dev/zero of="$MNT/zero.fill" bs=4M status=none || true
    rm -f "$MNT/zero.fill"
fi
df -h "$MNT" "$MNT/boot/firmware"
umount "$MNT/boot/firmware" "$MNT"
e2fsck -pf "$ROOT_DEV"

echo "==> compressing to $(basename "$OUT").xz"
xz -T0 -6 -c "$IMG" > "$OUT.xz.partial"
mv "$OUT.xz.partial" "$OUT.xz"
(cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT").xz" > "$(basename "$OUT").xz.sha256")
ls -la "$OUT.xz"
