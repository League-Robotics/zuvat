"""Save zuvat's latest camera frame, run ON the Pi: /opt/vision/bin/python zcam.py OUT.jpg

Takes it from zcamd's /snap.jpg when the viewer is running (it owns the camera),
otherwise opens the camera directly.
"""
import subprocess
import sys
import urllib.request

try:
    data = urllib.request.urlopen('http://127.0.0.1:8000/snap.jpg', timeout=3).read()
    open(sys.argv[1], 'wb').write(data)
    print(sys.argv[1], 'from zcamd')
    sys.exit()
except OSError:
    pass

import cv2  # noqa: E402

subprocess.run(['v4l2-ctl', '-d', '/dev/video0', '-c', 'power_line_frequency=2'], check=False)
cam = cv2.VideoCapture(0)
cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
for _ in range(12):
    ok, frame = cam.read()
cv2.imwrite(sys.argv[1], frame)
print(sys.argv[1], frame.shape)
