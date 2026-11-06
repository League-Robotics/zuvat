"""One camera-checked move at a time toward picking up a can or placing the held can.

    uv run --project ../pxt-nezha-diffdrive python tools/zcan.py look
    ... zcan.py pick CAN [east|west|north|south]   next move toward gripping can tag CAN
    ... zcan.py place TARGET                       next move toward dropping the held can on TARGET
    ... zcan.py back CM                            reverse CM
    ... zcan.py grip DEG                           set the gripper (30 open, 80 closed)
    ... zcan.py zcam NAME                          save a robot-camera frame as captures/NAME.jpg

The approach side names where the robot comes FROM. Each call prints the plan, makes at
most one move, and prints where the robot landed. 'done' means the phase is finished.
"""
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from aprilcam.client.discovery import Discovery

sys.path.insert(0, str(Path(__file__).parent))
from zvision import DAEMON, look  # noqa: E402

PI = 'jtl@192.168.5.216'
CAPTURES = Path(__file__).resolve().parents[1] / 'captures'
GRIP_FWD = 16.2       # cm, gripper ring centre ahead of the robot tag
HELD_FWD = 19.0       # cm, a held can's centre ahead of the robot tag (it rides the ring's front)
PRE = 14.0            # cm, extra stand-off before the final straight approach
OPEN, CLOSED = 40, 80
TURN_GAIN = 1.12      # pivots land 70-90 % of command on camera (right wheel slips)
MAX_LEG = 20.0        # cm per straight move: the right wheel slips
VEER = 0.42           # deg/cm the robot turns right driving forward
LINE_TOL, HEAD_TOL, DIST_TOL = 1.5, 3.0, 1.0
FENCE = (-55.0, 50.0, -36.0, 30.0)   # robot centre x0 x1 y0 y1
TARGETS = {'purple': (-38.1, 20.3), 'black': (-3.4, 21.8), 'yellow': (31.0, 22.7),
           'blue': (-36.9, -28.3), 'grey': (-1.7, -26.2), 'green': (32.8, -24.9),
           'orangeNW': (-53.1, 25.9), 'orangeNE': (46.1, 29.5),
           'orangeSW': (-52.1, -35.0), 'orangeSE': (47.9, -31.2)}   # bare-wood field, 2026-11-05
SIDES = {'east': (-1, 0), 'west': (1, 0), 'north': (0, -1), 'south': (0, 1),
         'southwest': (0.7071, 0.7071), 'southeast': (-0.7071, 0.7071)}


def ssh(*cmd):
    out = subprocess.run(['ssh', PI, *cmd], capture_output=True, text=True)
    lines = out.stdout.strip().splitlines()
    if out.returncode or not lines:
        raise SystemExit(f'ssh failed: {out.stderr.strip()[-300:]}')
    return lines


def move(mm, deg, speed=80):
    r = json.loads(ssh('/opt/vision/bin/python', 'zlink.py', 'move', str(int(round(mm))),
                       f'{deg:.1f}', str(speed))[-1])
    return r['status'].get('reason'), r['status'].get('i2cf')


def grip(deg):
    return json.loads(ssh('/opt/vision/bin/python', 'zlink.py', 'cmd', f"'RUN grip {deg} 1'")[-1])['replies']


def zcam(name):
    ssh('/opt/vision/bin/python', 'zcam.py', '/tmp/zc.jpg')
    path = CAPTURES / f'{name}.jpg'
    subprocess.run(['scp', '-q', f'{PI}:/tmp/zc.jpg', str(path)], check=True)
    return path


def wrap(a):
    return (a + 180) % 360 - 180


def fmt(p):
    return 'unseen' if p is None else f'({p[0]:.1f}, {p[1]:.1f})' + (f' h {p[2]:.1f}' if len(p) > 2 else '')


def fenced(x, y):
    x0, x1, y0, y1 = FENCE
    return x0 <= x <= x1 and y0 <= y <= y1


OBSTACLES = []        # (x, y) of cans the pivot must not sweep, set per call
SWEEP = (8.0, 26.0)   # cm from the robot centre the arms or a held can pass through


def turn_to(r, heading, why):
    err = wrap(heading - r[2])
    if abs(err) > 15:
        def swept(o):
            b = wrap(math.degrees(math.atan2(o[1] - r[1], o[0] - r[0])) - r[2])
            lo, hi = sorted((0.0, err))
            return lo - 20 <= b <= hi + 20
        near = [o for o in OBSTACLES
                if SWEEP[0] < math.hypot(o[0] - r[0], o[1] - r[1]) < SWEEP[1] and swept(o)]
        if near:
            print(f'plan: back 10 cm first, a can at {fmt(near[0])} is in the pivot sweep')
            return move(-100, 0)
    print(f'plan: pivot {err:+.1f} deg to face {heading:.0f} ({why})')
    return move(0, err * TURN_GAIN)


CORRIDOR = 12.3      # cm: robot half-width 9 + a can's radius


def drive(cm, why, r=None):
    leg = max(-MAX_LEG, min(MAX_LEG, cm))
    if r is not None:
        h = math.radians(r[2])
        for o in OBSTACLES:
            along = (o[0] - r[0]) * math.cos(h) + (o[1] - r[1]) * math.sin(h)
            side = abs(-(o[0] - r[0]) * math.sin(h) + (o[1] - r[1]) * math.cos(h))
            reach = (min(0, leg) - 13, max(0, leg) + 13)
            if reach[0] < along < reach[1] and side < CORRIDOR:
                print(f'blocked: a can at {fmt(o)} is {side:.1f} cm off the path of a {leg:+.1f} cm leg')
                return None
    print(f'plan: drive {leg:+.1f} cm of {cm:+.1f} ({why})')
    return move(leg * 10, 0)


def go_point(r, x, y, why, final_heading=None):
    """One move toward (x, y); then turn to final_heading. Returns True when there."""
    dx, dy = x - r[0], y - r[1]
    dist = math.hypot(dx, dy)
    if dist > LINE_TOL:
        bearing = math.degrees(math.atan2(dy, dx))
        err = wrap(bearing - r[2])
        if abs(err) > 140 and dist < 8:
            drive(dist * math.cos(math.radians(err)), f'reverse toward {why}')
            return False
        aim = bearing + VEER * min(dist, MAX_LEG) / 2
        if abs(wrap(aim - r[2])) > (4.0 if dist > 20 else HEAD_TOL):
            turn_to(r, aim, f'toward {why}, {aim - bearing:+.1f} for the veer')
        else:
            drive(dist, f'to {why}', r)
        return False
    if final_heading is not None and abs(wrap(final_heading - r[2])) > HEAD_TOL:
        turn_to(r, final_heading, f'line up at {why}')
        return False
    return True


def pick(lk, can, side):
    r, cans = lk.robot(), lk.cans()
    c = can if isinstance(can, tuple) else cans.get(can)
    OBSTACLES[:] = [xy for n, xy in cans.items() if n != can and n != 1 and xy != c]
    if r is None or c is None:
        print(f'robot {fmt(r)}, can {can} {fmt(c)}: cannot plan')
        return
    ux, uy = (SIDES[side] if side else
              (np.array(c) - np.array(r[:2])) / max(1e-6, math.hypot(c[0] - r[0], c[1] - r[1])))
    ux, uy = float(ux), float(uy)
    heading = math.degrees(math.atan2(uy, ux))
    rel = np.array(r[:2]) - np.array(c)
    s = rel[0] * ux + rel[1] * uy                 # along the approach line, negative = behind the can
    e = -rel[0] * uy + rel[1] * ux                # left of the line
    print(f'robot {fmt(r)}  can {can} {fmt(c)}  approach heading {heading:.0f}  along {s:.1f} side {e:+.1f}')
    pre = (c[0] - (GRIP_FWD + PRE) * ux, c[1] - (GRIP_FWD + PRE) * uy)
    if not fenced(*pre):
        print(f'pre-point {fmt(pre)} is outside the fence {FENCE}: pick another side')
        return
    on_line = abs(e) <= 3.0 and -(GRIP_FWD + PRE + 4) <= s <= -GRIP_FWD + 2
    if not on_line:
        go_point(r, *pre, f'pre-point {fmt(pre)}', heading)
        return
    to_can = math.hypot(c[0] - r[0], c[1] - r[1])
    gap = to_can - GRIP_FWD
    aim = math.degrees(math.atan2(c[1] - r[1], c[0] - r[0])) + VEER * max(gap, 0) / 2
    if abs(wrap(aim - r[2])) > 2.0:
        turn_to(r, aim, 'aim the ring at the can')
        return
    if abs(gap) > DIST_TOL:
        grip(OPEN)
        drive(gap, 'ring over the can')
        return
    print('plan: close the gripper')
    print(grip(CLOSED))
    print('done: can in the ring')


def place(lk, target):
    r, targets = lk.robot(), TARGETS
    if r:
        held = (r[0] + HELD_FWD * math.cos(math.radians(r[2])), r[1] + HELD_FWD * math.sin(math.radians(r[2])))
        OBSTACLES[:] = [xy for n, xy in lk.cans().items() if n != 1 and math.hypot(xy[0] - held[0], xy[1] - held[1]) > 5]
    t = targets.get(target)
    if r is None or t is None:
        print(f'robot {fmt(r)}, {target} {fmt(t)} (seen: {sorted(targets)}): cannot plan')
        return
    dx, dy = t[0] - r[0], t[1] - r[1]
    dist = math.hypot(dx, dy)
    bearing = math.degrees(math.atan2(dy, dx))
    ring = (r[0] + HELD_FWD * math.cos(math.radians(r[2])), r[1] + HELD_FWD * math.sin(math.radians(r[2])))
    miss = math.hypot(ring[0] - t[0], ring[1] - t[1])
    print(f'robot {fmt(r)}  {target} {fmt(t)}  ring {fmt(ring)}  ring miss {miss:.1f} cm')
    if miss <= 1.5:
        print('plan: open the gripper, back out 15 cm')
        print(grip(OPEN))
        print(move(-150, 0))
        print('done: can placed')
        return
    aim = bearing + VEER * min(max(dist - HELD_FWD, 0), MAX_LEG) / 2
    if abs(wrap(aim - r[2])) > HEAD_TOL and dist > HELD_FWD - 3:
        turn_to(r, aim, f'face {target}, {aim - bearing:+.1f} for the veer')
        return
    end = (r[0] + (dist - HELD_FWD) * dx / dist, r[1] + (dist - HELD_FWD) * dy / dist)
    if not fenced(*end):
        print(f'end {fmt(end)} is outside the fence: cannot reach {target} straight')
        return
    drive(dist - HELD_FWD, f'ring onto {target}', r)


def report(d):
    time.sleep(0.3)
    lk = look(d)
    r = lk.robot()
    ring = lk.ring()
    print(f'landed: robot {fmt(r)}  ring {fmt(ring)}  frame {lk.path.name}')


if __name__ == '__main__':
    verb, args = sys.argv[1], sys.argv[2:]
    d = Discovery().connect(DAEMON)
    if verb == 'look':
        lk = look(d)
        print('robot', fmt(lk.robot()), ' ring', fmt(lk.ring()))
        print('cans', {n: fmt(c) for n, c in sorted(lk.cans().items())})
        print('targets', {n: fmt(t) for n, t in sorted(lk.targets().items())})
        sys.exit()
    if verb == 'grip':
        print(grip(int(args[0])))
        sys.exit()
    if verb == 'zcam':
        print(zcam(args[0]))
        sys.exit()
    if verb == 'back':
        print(move(-float(args[0]) * 10, 0))
    elif verb == 'pick':
        can = tuple(map(float, args[0].split(','))) if ',' in args[0] else int(args[0])
        pick(look(d, save=False), can, args[1] if len(args) > 1 else None)
    elif verb == 'goto':
        lk = look(d, save=False)
        OBSTACLES[:] = [xy for n, xy in lk.cans().items() if n != 1]
        if go_point(lk.robot(), float(args[0]), float(args[1]), f'({args[0]}, {args[1]})',
                    float(args[2]) if len(args) > 2 else None):
            print('done: there')
    elif verb == 'place':
        place(look(d, save=False), args[0])
    report(d)
