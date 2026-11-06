"""One overhead look at playfield 4 from angst: robot pose, cans, gripper ring and targets in field cm.

    uv run --project ../pxt-nezha-diffdrive python tools/zvision.py [OUT.jpg]

Tags are found here (angst's daemon misses most of them) and mapped to the floor with a
homography from the field's ArUco markers. A tag at height h reads too far from the
camera's nadir by H/(H-h); that is undone with CAMERA_H, fitted from the robot tag
(12.6 cm) reading 12 % long.
"""
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from aprilcam.client.discovery import Discovery

DAEMON = '127.0.0.1:5280'
CAMERA = 'arducam-ov9782-usb-camera'
ROBOT_TAG = 100
ROBOT_TAG_H = 12.6
CAN_H = 12.2
CAMERA_H = 118.0
CAPTURES = Path(__file__).resolve().parents[1] / 'captures'
CLAHE = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
DETECTOR = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11))
TARGET_COLOURS = {'blue': ((95, 120, 80), (115, 255, 255)), 'grey': ((0, 0, 140), (179, 40, 210)),
                  'green': ((70, 100, 60), (90, 255, 220)), 'orange': ((18, 80, 200), (36, 200, 255))}


class Look:
    def __init__(self, frame):
        self.image = cv2.imdecode(np.frombuffer(frame.data, np.uint8), cv2.IMREAD_COLOR)
        src, dst = [], []
        for t in frame.tags.tags if frame.tags else ():
            if t.tag.family.value == 'aruco' and t.world_corners and t.pixel_corners:
                src += [(c.x, c.y) for c in t.pixel_corners]
                dst += [(c.x, c.y) for c in t.world_corners]
        self.H, _ = cv2.findHomography(np.float32(src), np.float32(dst), cv2.RANSAC, 3.0)
        h, w = self.image.shape[:2]
        self.nadir = self.floor([(w / 2, h / 2)])[0]
        self.tags = self._tags()

    def floor(self, px):
        return cv2.perspectiveTransform(np.float32(px).reshape(-1, 1, 2), self.H).reshape(-1, 2)

    def raised(self, xy, height):
        return self.nadir + (np.asarray(xy) - self.nadir) * (CAMERA_H - height) / CAMERA_H

    def _tags(self):
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        found = {}
        for g in (gray, CLAHE.apply(gray), cv2.normalize(CLAHE.apply(gray), None, 0, 255, cv2.NORM_MINMAX)):
            corners, ids, _ = DETECTOR.detectMarkers(g)
            for c, i in zip(corners, ids.ravel() if ids is not None else ()):
                found.setdefault(int(i), c.reshape(4, 2))
        return found

    def tag_pose(self, n, height):
        px = self.tags.get(n)
        if px is None:
            return None
        w = np.array([self.raised(p, height) for p in self.floor(px)])
        cx, cy = w.mean(axis=0)
        fwd = (w[0] + w[1]) / 2 - (w[3] + w[2]) / 2
        return float(cx), float(cy), math.degrees(math.atan2(fwd[1], fwd[0]))

    def robot(self):
        return self.tag_pose(ROBOT_TAG, ROBOT_TAG_H)

    def cans(self):
        return {n: self.tag_pose(n, CAN_H)[:2] for n in self.tags if n != ROBOT_TAG}

    def ring(self):
        """Centre of the green gripper ring near the robot, floor cm, or None."""
        r = self.robot()
        if r is None:
            return None
        hsv = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (40, 90, 90), (85, 255, 255))
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return None
        w = self.floor(np.stack([xs, ys], axis=1))
        h = math.radians(r[2])
        fwd = (w[:, 0] - r[0]) * math.cos(h) + (w[:, 1] - r[1]) * math.sin(h)
        side = -(w[:, 0] - r[0]) * math.sin(h) + (w[:, 1] - r[1]) * math.cos(h)
        pick = w[(fwd > 13) & (fwd < 32) & (np.abs(side) < 8)]
        return None if len(pick) < 30 else tuple(map(float, pick.mean(axis=0)))

    def targets(self):
        """Coloured squares and orange dots on the wooden half: name -> (x, y) floor cm."""
        hsv = cv2.cvtColor(cv2.GaussianBlur(self.image, (5, 5), 0), cv2.COLOR_BGR2HSV)
        h = self.image.shape[0]
        out = {}
        for name, (lo, hi) in TARGET_COLOURS.items():
            mask = cv2.inRange(hsv, lo, hi)
            mask[: int(h * 0.68)] = 0
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
            blobs = []
            for i in range(1, n):
                x, y = self.floor([cents[i]])[0]
                if 12 < stats[i, cv2.CC_STAT_AREA] < 3000 and -64 < x < 62 and -46 < y < -14:
                    blobs.append((stats[i, cv2.CC_STAT_AREA], (float(x), float(y))))
            if name != 'orange':
                blobs = sorted(blobs, reverse=True)[:1]
            for k, (_, xy) in enumerate(sorted(blobs, key=lambda b: b[1][0])):
                out[f'{name}{k + 1}' if name == 'orange' else name] = xy
        return out


def look(d, save=True):
    asked = time.time()
    while True:
        f = d.get_frame(CAMERA)
        if time.time() - asked > 1.2 and f.timestamp > asked + 0.8:
            break
        time.sleep(0.1)
    lk = Look(f)
    if save:
        CAPTURES.mkdir(exist_ok=True)
        lk.path = CAPTURES / f'look-{time.strftime("%H%M%S")}.jpg'
        cv2.imwrite(str(lk.path), lk.image)
    return lk


if __name__ == '__main__':
    lk = look(Discovery().connect(DAEMON))
    r = lk.robot()
    print('nadir', np.round(lk.nadir, 1))
    print('robot', None if r is None else tuple(round(v, 1) for v in r))
    print('ring', lk.ring() and tuple(round(v, 1) for v in lk.ring()))
    for n, xy in sorted(lk.cans().items()):
        print(f'can {n:3d}', tuple(round(v, 1) for v in xy))
    for n, xy in sorted(lk.targets().items()):
        print(f'{n:8s}', tuple(round(v, 1) for v in xy))
    print(lk.path)
