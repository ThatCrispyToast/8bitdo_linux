#!/usr/bin/env python3
"""Print the input reports a device sends while you press its buttons.

Read-only: it opens the hidraw nodes alongside the kernel driver and never writes.
Used to find out which button-table entry drives which physical input on the R8:
map distinctive test functions to the entries under investigation (a keyboard key
such as F13/F14 or a horizontal scroll works well), run this, press the buttons,
then restore the map.  The R8's mouse interface (iface 0) reports
``[1, buttons, x lo, x hi, y lo, y hi, wheel, pan]`` and its keyboard interface
(iface 1) ``[1, modifiers, 0, usage x6]``.  Pure motion reports are skipped and
consecutive identical reports collapsed, so the output is one line per event.

    python3 tools/reverse/hid_capture.py 120 /dev/hidraw0 /dev/hidraw1
"""
import os
import select
import sys
import time


def main(seconds: float, nodes) -> None:
    fds = {os.open(n, os.O_RDONLY | os.O_NONBLOCK): n for n in nodes}
    t0 = time.time()
    last = {}
    print(f"capturing {seconds:g} s on {' '.join(nodes)}", flush=True)
    while time.time() - t0 < seconds:
        ready, _, _ = select.select(list(fds), [], [], 0.2)
        for fd in ready:
            try:
                d = os.read(fd, 64)
            except BlockingIOError:
                continue
            n = fds[fd]
            if len(d) == 8 and d[0] == 1 and d[1] == 0 and d[6] == 0 and d[7] == 0:
                continue  # R8 mouse report with motion only
            if last.get(n) == d:
                continue
            last[n] = d
            print(f"{time.time() - t0:7.2f} {os.path.basename(n)} {d.hex()}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(float(sys.argv[1]), sys.argv[2:])
