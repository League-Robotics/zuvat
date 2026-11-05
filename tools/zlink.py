"""Serial link to the robot's micro:bit, run ON the Pi (its /opt/vision Python has mbtools).

    /opt/vision/bin/python zlink.py move MM DEG [SPEED]   MOVE_X, polled to completion
    /opt/vision/bin/python zlink.py cmd 'VERB ARGS' ...    sequenced commands, replies printed
    /opt/vision/bin/python zlink.py watch 'RUN calwheels 90.2 0' SECS   run a program, print its lines live
    /opt/vision/bin/python zlink.py status

Prints one JSON object on its last line for the host to parse.
"""
import json
import math
import sys
import time

from mbtools.registry.client import RegistryClient
from mbtools.serial.connect import connect

ROBOT = 'zuvat'
SOCKET = '/run/mbregistry/api.sock'


class Link:
    def __init__(self):
        self.client = RegistryClient(SOCKET)
        self.s = connect(self.client, ROBOT)
        self.seq = 0
        self.t0 = time.time()

    def write(self, line):
        self.s.write((line + '\n').encode())
        self.s.flush()

    def read_for(self, secs):
        out, end = [], time.time() + secs
        while time.time() < end:
            raw = self.s.readline()
            if not raw:
                continue
            line = raw.decode(errors='replace').strip()
            if line and not line.startswith('DBG'):
                out.append(line)
        return out

    def hello(self):
        self.write('HELLO')
        self.read_for(0.4)
        self.seq = 0

    def cmd(self, line, wait=0.4):
        self.seq += 1
        self.write(f'{line} #{self.seq}')
        return self.read_for(wait)

    def status(self):
        self.write('STATUS')
        for line in self.read_for(0.3):
            if line.startswith('status '):
                return dict(kv.split('=', 1) for kv in line.split()[1:] if '=' in kv)
        return {}

    def odom(self):
        """x y [mm], h [cdeg], posl posr [counts] from one TLM FULL row."""
        for _ in range(3):
            hdr = None
            rows = self.cmd('TLM FULL', 0.6)
            self.cmd('TLM OFF', 0.3)
            for line in reversed(rows):
                f = line.split()
                if f[0] == 'thdr':
                    hdr = f[1:]
            for line in reversed(rows):
                f = line.split()
                if f[0] == 't' and hdr and len(f) - 1 == len(hdr):
                    r = dict(zip(hdr, f[1:]))
                    return {k: float(r[k]) for k in ('x', 'y', 'h', 'posl', 'posr', 'i2cf')}
        return {}

    def close(self):
        self.s.close()


def main():
    verb, args = sys.argv[1], sys.argv[2:]
    link = Link()
    try:
        link.hello()
        result = {}
        if verb == 'move':
            mm, deg = float(args[0]), float(args[1])
            speed = int(args[2]) if len(args) > 2 else 60
            before = link.odom()
            replies = link.cmd(f'MOVE_X {int(round(mm))} {int(round(math.radians(deg) * 1000))} {speed} 15000', 0.2)
            t = time.time()
            st, started = {}, False
            while time.time() - t < 20:
                st = link.status()
                started = started or st.get('active') == '1'
                if st.get('active') == '0' and (started or time.time() - t > 1.0):
                    break
            after = link.odom()
            result = {'replies': replies, 'secs': round(time.time() - t, 2), 'status': st,
                      'before': before, 'after': after}
        elif verb == 'watch':
            secs, end_marks = float(args[1]), ('.fail', '.stored', '.restored', 'stopped')
            link.cmd(args[0], 0.0)
            t, ended, last = time.time(), None, time.time()
            while (time.time() - t < secs and (ended is None or time.time() - ended < 8)
                   and time.time() - last < 25):
                for line in link.read_for(0.5):
                    last = time.time()
                    print(f'{time.time() - t:6.1f} {line}', flush=True)
                    if ended is None and any(m in line for m in end_marks):
                        ended = time.time()
            result = {'status': link.status()}
        elif verb == 'cmd':
            result = {'replies': [r for a in args for r in link.cmd(a, 0.6)]}
        elif verb == 'status':
            result = {'status': link.status(), 'odom': link.odom()}
        print(json.dumps(result))
    finally:
        link.close()


if __name__ == '__main__':
    main()
