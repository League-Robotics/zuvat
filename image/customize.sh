#!/bin/bash
# Runs inside the image's root filesystem (chroot), from /tmp/zuvat.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
cd /tmp/zuvat

MACHINE_ID="$(cat /etc/machine-id)"
MBTOOLS_VERSION="${MBTOOLS_VERSION:-latest}"

printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d

apt-get update
apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold full-upgrade
grep -v -E '^\s*(#|$)' packages.txt | xargs apt-get install -y --no-install-recommends

if [ "$MBTOOLS_VERSION" = latest ]; then
    MBTOOLS_URL=https://github.com/League-Microbit/mbtools/releases/latest/download/mbtools_arm64.deb
else
    MBTOOLS_URL="https://github.com/League-Microbit/mbtools/releases/download/v$MBTOOLS_VERSION/mbtools_${MBTOOLS_VERSION}_arm64.deb"
fi
curl -fsSL -o mbtools.deb "$MBTOOLS_URL"
apt-get install -y ./mbtools.deb
curl -fsSL -o /usr/local/sbin/mbtools-update \
    https://raw.githubusercontent.com/League-Microbit/mbtools/main/packaging/deb/install-mbtools.sh
chmod 755 /usr/local/sbin/mbtools-update

curl -fsSL https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-unknown-linux-gnu.tar.gz \
    | tar -xz --strip-components=1 -C /usr/local/bin uv-aarch64-unknown-linux-gnu/uv uv-aarch64-unknown-linux-gnu/uvx

python3 -m venv /opt/vision
/opt/vision/bin/pip install --no-cache-dir --upgrade pip
/opt/vision/bin/pip install --no-cache-dir -r requirements-vision.txt ./aprilcam-*.whl
PYVER="$(/opt/vision/bin/python -c 'import sys; print(f"python{sys.version_info[0]}.{sys.version_info[1]}")')"
echo "/usr/lib/mbtools/venv/lib/$PYVER/site-packages" > "/opt/vision/lib/$PYVER/site-packages/mbtools.pth"
/opt/vision/bin/python -c 'import cv2, numpy, aprilcam, mbtools; cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)'
echo 'PATH="/opt/vision/bin:$PATH"' > /etc/profile.d/vision.sh

sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8
ln -sf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime
echo America/Los_Angeles > /etc/timezone
sed -i 's/^XKBLAYOUT=.*/XKBLAYOUT="us"/' /etc/default/keyboard
grep -q ieee80211_regdom /boot/firmware/cmdline.txt \
    || sed -i '1 s/$/ cfg80211.ieee80211_regdom=US/' /boot/firmware/cmdline.txt

systemctl enable ssh.service mbregistry.service
getent passwd 1000 | grep -q '^pi:' || { echo "the seed's user is made by renaming uid 1000 (pi); it is missing" >&2; exit 1; }

mkdir -p /etc/zuvat-image
{
    echo "built=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "base=$BASE_IMAGE"
    echo "mbtools=$(dpkg-query -W -f '${Version}' mbtools)"
    echo "aprilcam=$(/opt/vision/bin/python -c 'import importlib.metadata as m; print(m.version("aprilcam"))')"
    echo "opencv=$(/opt/vision/bin/python -c 'import cv2; print(cv2.__version__)')"
    echo "uv=$(/usr/local/bin/uv --version | cut -d' ' -f2)"
    echo "kernel=$(ls /lib/modules | sort -V | tail -1)"
} > /etc/zuvat-image/release
/opt/vision/bin/pip freeze > /etc/zuvat-image/vision-freeze.txt
dpkg-query -W -f '${Package}\t${Version}\n' > /etc/zuvat-image/packages.tsv

rm -f /usr/sbin/policy-rc.d /etc/ssh/ssh_host_*
apt-get clean
rm -rf /var/lib/apt/lists/* /root/.cache
cloud-init clean --logs
printf '%s\n' "$MACHINE_ID" > /etc/machine-id
