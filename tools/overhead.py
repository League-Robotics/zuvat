"""Overhead view of the main playfield from angst: tags seen, and a saved frame.

    uv run --project ../pxt-nezha-diffdrive python tools/overhead.py [OUT.jpg]
"""
import sys
import time
from pathlib import Path

from aprilcam.client.discovery import Discovery

HOST = '127.0.0.1:5280'  # angst, tunnelled: gala's Python is blocked from the LAN
CAMERA = 'arducam-ov9782-usb-camera'
ROOT = Path(__file__).resolve().parents[1]

d = Discovery().connect(HOST)
for frame in d.stream_tags(CAMERA):
    for t in sorted(frame.tags or (), key=lambda t: (t.tag.family.value, t.tag.number)):
        w = f'({t.world.x:6.1f},{t.world.y:6.1f}) yaw {t.yaw_rad:+.2f}' if t.world else 'no world pose'
        print(f'{t.tag.family.value:8} {t.tag.number:4}  {w}')
    break
out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'captures' / f'overhead-{time.strftime("%Y%m%d-%H%M%S")}.jpg'
out.parent.mkdir(parents=True, exist_ok=True)
print(d.get_frame(CAMERA, format='file', path=str(out)) or out)
