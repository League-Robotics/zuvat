#!/bin/bash
# Runs in the zuvat-imager container: boots cloud-init in a chroot of the
# image with the seed in /repo/$2 and checks the user it makes.
# Usage: firstboot-test.sh IMAGE.img.xz SEEDDIR  (paths relative to /repo)
set -uo pipefail

IMG=/work/test.img
MNT=/mnt/test
FAILS=0
mkdir -p /work "$MNT"
xz -dc -T0 "/repo/$1" > "$IMG"

attach() {
    local start sectors
    read -r start sectors < <(partx -g -n "$1" -o START,SECTORS "$IMG")
    losetup -f --show -o $((start * 512)) --sizelimit $((sectors * 512)) "$IMG"
}
ROOT_DEV="$(attach 2)"
BOOT_DEV="$(attach 1)"
trap 'umount -R "$MNT" 2>/dev/null; losetup -d "$ROOT_DEV" "$BOOT_DEV"' EXIT
mount "$ROOT_DEV" "$MNT"
mount "$BOOT_DEV" "$MNT/boot/firmware"
mount -t proc proc "$MNT/proc"
mount -t sysfs sys "$MNT/sys"
mount --bind /dev "$MNT/dev"
cp "/repo/$2"/user-data "/repo/$2"/network-config "/repo/$2"/meta-data "$MNT/boot/firmware/"

printf '#!/bin/sh\nfor a; do shift; [ "$a" = --now ] || set -- "$@" "$a"; done\nexec /usr/bin/systemctl "$@"\n' \
    > "$MNT/usr/local/bin/systemctl"
chmod 755 "$MNT/usr/local/bin/systemctl"

chroot "$MNT" cloud-init init --local > /dev/null 2>&1
chroot "$MNT" cloud-init init > /dev/null 2>&1
chroot "$MNT" cloud-init modules --mode config > /dev/null 2>&1
chroot "$MNT" cloud-init modules --mode final > /dev/null 2>&1

check() {
    if eval "$2"; then echo "  ok    $1"; else echo "  FAIL  $1"; FAILS=$((FAILS + 1)); fi
}
echo "first-boot checks:"
check "hostname is zuvat" '[ "$(cat $MNT/etc/hostname)" = zuvat ]'
check "jtl is uid 1000" '[ "$(chroot $MNT id -u jtl 2>/dev/null)" = 1000 ]'
check "pi is gone" '! grep -q "^pi:" $MNT/etc/passwd'
check "jtl has 3 SSH keys" '[ "$(grep -c "^ssh-" $MNT/home/jtl/.ssh/authorized_keys 2>/dev/null)" = 3 ]'
check "authorized_keys owned by jtl" '[ "$(chroot $MNT stat -c %U /home/jtl/.ssh/authorized_keys 2>/dev/null)" = jtl ]'
check "jtl has a password" 'chroot $MNT passwd -S jtl | grep -q " P "'
check "jtl has passwordless sudo" 'grep -rqs "^jtl ALL=(ALL) NOPASSWD:ALL" $MNT/etc/sudoers.d'
check "jtl in plugdev, dialout, video" 'chroot $MNT id -nG jtl | tr " " "\n" | grep -cxE "plugdev|dialout|video" | grep -qx 3'
check "/opt/vision owned by jtl" '[ "$(chroot $MNT stat -c %U /opt/vision/bin/python3)" = jtl ]'
check "userconfig wizard masked" '[ "$(readlink $MNT/etc/systemd/system/userconfig.service)" = /dev/null ]'
check "no failed cloud-init modules" '! grep -E "Running module .* failed" $MNT/var/log/cloud-init.log | grep -v netplan_nm_patch | grep -q .'
grep -E "Running module .* failed" "$MNT/var/log/cloud-init.log" | sed 's/^/        /' | head -5

[ "$FAILS" = 0 ] && echo "first boot: all checks passed" || { echo "first boot: $FAILS check(s) failed"; exit 1; }
