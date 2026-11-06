"""Live view of zuvat's camera, run ON the Pi: /opt/vision/bin/python zcamd.py [PORT]

    http://<pi>:8000/          page with the live stream
    http://<pi>:8000/stream    MJPEG
    http://<pi>:8000/snap.jpg  latest frame

One thread owns /dev/video0; everything else reads its latest frame.
"""
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
DEVICE = '/dev/v4l/by-id/usb-Sonix_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-video-index0'
PAGE = b"""<!doctype html><html><head><meta name=viewport content="width=device-width">
<title>zuvat camera</title><style>body{margin:0;background:#111;color:#ccc;font:14px sans-serif}
img{display:block;width:100%;max-width:1280px;margin:auto}p{text-align:center}</style></head>
<body><img src="/stream"><p>zuvat camera</p></body></html>"""

latest = None
lock = threading.Lock()


def capture():
    global latest
    cam, fails = None, 0
    while True:
        if cam is None:
            subprocess.run(['v4l2-ctl', '-d', DEVICE, '-c', 'power_line_frequency=2'], check=False)
            cam = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        ok, frame = cam.read()
        if not ok:
            fails += 1
            if fails > 10:
                cam.release()
                cam, fails = None, 0
                with lock:
                    latest = None
            time.sleep(0.3)
            continue
        fails = 0
        ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with lock:
                latest = jpg.tobytes()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE)
        elif self.path.startswith('/snap.jpg'):
            with lock:
                data = latest
            if data is None:
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    with lock:
                        data = latest
                    if data:
                        self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                                         + str(len(data)).encode() + b'\r\n\r\n' + data + b'\r\n')
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


threading.Thread(target=capture, daemon=True).start()
ThreadingHTTPServer(('', PORT), Handler).serve_forever()
