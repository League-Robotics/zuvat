#!/usr/bin/env bash
# Build build/zuvat-YYYYMMDD.img.xz from Raspberry Pi OS Lite (arm64).
# Needs Docker on an arm64 host (the chroot runs natively, no emulation).
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_NAME=2026-10-06-raspios-trixie-arm64-lite.img.xz
BASE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-10-06/$BASE_NAME"
BASE_SHA256=483db18a48da399b5b7022ffae9a07bc6d99daab30e593aedac09b69ff422843
APRILCAM_SRC="${APRILCAM_SRC:-../aprilcam}"
OUT="build/zuvat-$(date +%Y%m%d).img"

mkdir -p build/wheels
if [ ! -f "build/$BASE_NAME" ]; then
    curl -fL -o "build/$BASE_NAME.partial" "$BASE_URL"
    mv "build/$BASE_NAME.partial" "build/$BASE_NAME"
fi
echo "$BASE_SHA256  build/$BASE_NAME" | shasum -a 256 -c -

rm -f build/wheels/aprilcam-*.whl
(cd "$APRILCAM_SRC" && uv build --wheel --out-dir "$OLDPWD/build/wheels")

docker build -q -t zuvat-imager image
docker run --rm --privileged -v "$PWD:/repo" -e MBTOOLS_VERSION -e GROW \
    zuvat-imager /repo/image/inside.sh "build/$BASE_NAME" "$OUT"
image/test.sh "$OUT.xz"
