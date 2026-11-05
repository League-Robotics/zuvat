"""Camera-checked driving for zuvat: overhead pose from angst, moves over serial on the Pi.

    uv run --project ../pxt-nezha-diffdrive python tools/zdrive.py pose
    ... zdrive.py move MM DEG [SPEED]     MOVE_X, then the new overhead pose
    ... zdrive.py raw 'VERB ARGS' ...     sequenced commands, prints the replies

gala's Python can't reach the LAN (busboom-home-network issue 2026-11-04), so angst's
gRPC comes through `ssh -fNL 5280:127.0.0.1:5280 jtl@192.168.4.26` and the robot through ssh.
angst's daemon doesn't detect tag 100 on zuvat, so the tag is found here in its frame and
mapped to the floor with a homography from the field's ArUco markers in the same frame.
"""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from aprilcam.client.discovery import Discovery

DAEMON = '127.0.0.1:5280'
CAMERA = 'arducam-ov9782-usb-camera'
PI = 'jtl@192.168.5.216'
ROBOT = 'zuvat'
TAG = 100
CAPTURES = Path(__file__).resolve().parents[1] / 'captures'
CLAHE = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
DETECTOR = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11))


def pose(d, save=True):
    """(x cm, y cm, tag heading deg) of tag 100 on the floor plane, or None."""
    asked = time.time()
    while True:
        f = d.get_frame(CAMERA)
        if time.time() - asked > 1.2 and f.timestamp > asked + 0.8:
            break
        time.sleep(0.1)
    im = cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR)
    src, dst = [], []
    for t in f.tags.tags if f.tags else ():
        if t.tag.family.value == 'aruco' and t.world_corners and t.pixel_corners:
            src += [(c.x, c.y) for c in t.pixel_corners]
            dst += [(c.x, c.y) for c in t.world_corners]
    H, _ = cv2.findHomography(np.float32(src), np.float32(dst), cv2.RANSAC, 3.0)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    for g in (gray, CLAHE.apply(gray), cv2.normalize(CLAHE.apply(gray), None, 0, 255, cv2.NORM_MINMAX)):
        corners, ids, _ = DETECTOR.detectMarkers(g)
        if ids is not None and TAG in ids.ravel():
            break
    if save:
        CAPTURES.mkdir(exist_ok=True)
        cv2.imwrite(str(CAPTURES / f'zdrive-{time.strftime("%H%M%S")}.jpg'), im)
    if ids is None or TAG not in ids.ravel():
        return None
    px = corners[list(ids.ravel()).index(TAG)].reshape(4, 2)
    w = cv2.perspectiveTransform(px.reshape(-1, 1, 2).astype(np.float32), H).reshape(4, 2)
    cx, cy = w.mean(axis=0)
    fwd = (w[0] + w[1]) / 2 - (w[3] + w[2]) / 2
    return float(cx), float(cy), math.degrees(math.atan2(fwd[1], fwd[0]))


def link(*args):
    """Run tools/zlink.py on the Pi (copied there as ~/zlink.py) and return its JSON result."""
    out = subprocess.run(['ssh', PI, '/opt/vision/bin/python', 'zlink.py', *map(str, args)],
                         capture_output=True, text=True)
    lines = out.stdout.strip().splitlines()
    if out.returncode or not lines:
        raise SystemExit(f'zlink failed: {out.stderr.strip()[-400:]}')
    return json.loads(lines[-1])


def show(p):
    return 'tag 100 not seen' if p is None else f'({p[0]:6.1f}, {p[1]:6.1f}) cm  tag heading {p[2]:6.1f} deg'


if __name__ == '__main__':
    verb, args = sys.argv[1], sys.argv[2:]
    d = Discovery().connect(DAEMON)
    if verb == 'pose':
        print(show(pose(d)))
    elif verb == 'move':
        before = pose(d, save=False)
        r = link('move', *args)
        time.sleep(0.5)
        after = pose(d)
        print('before', show(before))
        print('after ', show(after))
        if before and after:
            print(f'moved {math.hypot(after[0] - before[0], after[1] - before[1]):.1f} cm, '
                  f'turned {(after[2] - before[2] + 180) % 360 - 180:+.1f} deg')
        b, a, st = r['before'], r['after'], r['status']
        if a and b:
            print(f"odometry {math.hypot(a['x'] - b['x'], a['y'] - b['y']) / 10:.1f} cm, {(a['h'] - b['h']) / 100:+.1f} deg, "
                  f"wheels L {a['posl'] - b['posl']:+.0f} R {a['posr'] - b['posr']:+.0f} counts")
        print(' '.join(r['replies']), '|', f"{r['secs']} s", ' '.join(f'{k}={st.get(k)}' for k in ('active', 'done', 'reason', 'i2cf', 'wedge')))
    elif verb == 'raw':
        print(link('cmd', *args))
