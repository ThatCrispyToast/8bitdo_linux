"""Minimal hidraw transport for 8BitDo devices (Linux, stdlib only).

Devices are discovered through sysfs (/sys/class/hidraw) and opened as
/dev/hidrawN.  No libusb / hidapi needed.
"""
from __future__ import annotations

import fcntl
import os
import select
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

VENDOR_8BITDO = 0x2DC8

# ioctl helpers (linux/hidraw.h): HIDIOCSFEATURE(len) / HIDIOCGFEATURE(len)
_IOC_NRBITS, _IOC_TYPEBITS, _IOC_SIZEBITS = 8, 8, 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_WRITE, _IOC_READ = 1, 2


def _ioc(direction: int, typ: int, nr: int, size: int) -> int:
    return (direction << _IOC_DIRSHIFT) | (size << _IOC_SIZESHIFT) | (typ << _IOC_TYPESHIFT) | (nr << _IOC_NRSHIFT)


def HIDIOCSFEATURE(length: int) -> int:
    return _ioc(_IOC_WRITE | _IOC_READ, ord("H"), 0x06, length)


def HIDIOCGFEATURE(length: int) -> int:
    return _ioc(_IOC_WRITE | _IOC_READ, ord("H"), 0x07, length)


@dataclass
class HidrawInfo:
    """One hidraw node (= one USB HID interface)."""

    node: str  # e.g. /dev/hidraw2
    bus: int
    vid: int
    pid: int
    name: str
    phys: str
    uniq: str
    report_descriptor: bytes = field(repr=False, default=b"")

    @property
    def usage_page(self) -> Optional[int]:
        """Top-level usage page from the report descriptor (first item)."""
        d = self.report_descriptor
        if not d:
            return None
        tag = d[0]
        size = tag & 0x03
        if (tag & 0xFC) != 0x04:  # Global item: Usage Page
            return None
        if size == 1:
            return d[1]
        if size == 2:
            return d[1] | (d[2] << 8)
        return None

    @property
    def usb_interface(self) -> Optional[int]:
        """USB interface number, parsed from HID_PHYS (".../inputN")."""
        if "/input" in self.phys:
            try:
                return int(self.phys.rsplit("/input", 1)[1])
            except ValueError:
                return None
        return None


def enumerate_hidraw(vid: Optional[int] = None, pid: Optional[int] = None) -> Iterator[HidrawInfo]:
    base = Path("/sys/class/hidraw")
    if not base.exists():
        return
    for entry in sorted(base.iterdir(), key=lambda p: int(p.name[6:]) if p.name[6:].isdigit() else 0):
        dev = entry / "device"
        try:
            uevent = (dev / "uevent").read_text()
        except OSError:
            continue
        kv = dict(line.split("=", 1) for line in uevent.splitlines() if "=" in line)
        try:
            bus_s, vid_s, pid_s = kv.get("HID_ID", "0:0:0").split(":")
            bus, v, p = int(bus_s, 16), int(vid_s, 16), int(pid_s, 16)
        except ValueError:
            continue
        if vid is not None and v != vid:
            continue
        if pid is not None and p != pid:
            continue
        try:
            rd = (dev / "report_descriptor").read_bytes()
        except OSError:
            rd = b""
        yield HidrawInfo(
            node=f"/dev/{entry.name}",
            bus=bus,
            vid=v,
            pid=p,
            name=kv.get("HID_NAME", "").strip(),
            phys=kv.get("HID_PHYS", "").strip(),
            uniq=kv.get("HID_UNIQ", "").strip(),
            report_descriptor=rd,
        )


class HidrawDevice:
    """Blocking-with-timeout wrapper around a /dev/hidrawN node."""

    def __init__(self, node: str):
        self.node = node
        self.fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> "HidrawDevice":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- interrupt (input / output) reports -------------------------------
    def write(self, report_id: int, payload: bytes) -> int:
        """Send an output report.  report_id 0 = device uses no report IDs."""
        buf = bytes([report_id & 0xFF]) + bytes(payload)
        n = os.write(self.fd, buf)
        if n != len(buf):
            raise OSError(f"short write to {self.node}: {n}/{len(buf)}")
        return n

    def read(self, timeout: float, max_len: int = 256) -> Optional[bytes]:
        """Read one input report or None on timeout.

        For devices with numbered reports the first byte is the report ID.
        """
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        return os.read(self.fd, max_len)

    def drain(self, quiet: float = 0.02) -> int:
        """Discard pending input reports.  Returns number of reports dropped."""
        n = 0
        while True:
            r, _, _ = select.select([self.fd], [], [], quiet)
            if not r:
                return n
            os.read(self.fd, 256)
            n += 1

    # --- control (feature) reports ----------------------------------------
    def set_feature(self, report_id: int, payload: bytes) -> None:
        buf = bytearray([report_id & 0xFF]) + bytearray(payload)
        fcntl.ioctl(self.fd, HIDIOCSFEATURE(len(buf)), buf)

    def get_feature(self, report_id: int, length: int) -> bytes:
        buf = bytearray(length + 1)
        buf[0] = report_id & 0xFF
        fcntl.ioctl(self.fd, HIDIOCGFEATURE(len(buf)), buf)
        return bytes(buf)


def wait_for_reply(dev: HidrawDevice, predicate, timeout: float) -> Optional[bytes]:
    """Read reports until `predicate(report)` is true or the timeout elapses."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        rep = dev.read(remaining)
        if rep is None:
            return None
        if predicate(rep):
            return rep
