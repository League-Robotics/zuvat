#!/usr/bin/env bash
# First-boot test of an image with a dummy-secret seed: image/test.sh [IMAGE.img.xz]
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${1:-$(ls -t build/zuvat-*.img.xz | head -1)}"
mkdir -p build/seedtest
docker build -q -t zuvat-imager image >/dev/null
ROBOT_GARAGE_WIFI_PASSWORD=test-psk PI_JTL_PASSWORD=test-password image/seed.sh build/seedtest
docker run --rm --privileged -v "$PWD:/repo" zuvat-imager /repo/image/firstboot-test.sh "$IMAGE" build/seedtest
