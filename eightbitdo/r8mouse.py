"""8BitDo Retro R8 Mouse (USB 2dc8:5205) configuration protocol.

Reverse-engineered from 8BitDo Ultimate Software V2 (8BitDoAdvance.dll).

Transport: the vendor HID interface (usage page 0xFF00, 64-byte reports,
no report IDs).  Every request is::

    [0x01, class, command, op, payload...]        (padded to 64 bytes)

where ``op`` is 1 for a read and 4 for a write.  The reply is::

    [0x21, class, command, status, payload...]

``status`` has the request's ``op`` bit set on success (0x11 / 0x14).
All configuration commands use class 6.  The firmware version query uses
class 4.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .hidraw import HidrawDevice, HidrawInfo, enumerate_hidraw, wait_for_reply

VID = 0x2DC8
PID = 0x5205
PID_RECEIVER = 0x5206  # 2.4 GHz adapter (not handled here)
CONFIG_USAGE_PAGE = 0xFF00

OP_READ = 1
OP_WRITE = 4

CLS_INFO = 4
CLS_CONFIG = 6

CMD_RATE = 0x0D
CMD_MACRO = 0x0F
CMD_WRITE_MAP = 0x10
CMD_DPI_INDEX = 0x12
CMD_READ_MAP = 0x14
CMD_PROFILE_NAME = 0x1C
CMD_WHEEL_DIRECTION = 0x23
CMD_WHEEL_SPEED = 0x24
CMD_COLOR = 0x25
CMD_LOD = 0x26
CMD_LEFT_HAND = 0x27
# Buttons that can carry a macro -> macro storage slot (1..4, "num" in the app).
MACRO_SLOT = {3: 1, 4: 2, 5: 3, 6: 4}
CMD_DPI = 0x28
CMD_FACTORY_RESET = 0x33

DPI_MIN, DPI_MAX = 50, 26000
WHEEL_SPEED_MAX = 14
MACRO_MAX_RECORDS = 80
MACRO_NAME_BYTES = 30
PROFILE_NAME_BYTES = 20

# macro record key states
MACRO_KEY_PRESS = 10
MACRO_KEY_RELEASE = 2
MACRO_MOUSE_PRESS = 15
MACRO_MOUSE_RELEASE = 7

COLOR_NAMES = {0: "xbox", 1: "n-edition", 3: "c64", 7: "forest", 8: "gow"}


class R8Error(RuntimeError):
    pass


@dataclass
class DpiTable:
    enabled_mask: int            # bit i = slot i enabled (6 slots)
    values: List[int]            # 6 entries


@dataclass
class RateTable:
    count: int                   # number of usable rate slots (5 or 6)
    current: int                 # index of the active polling rate
    values: List[int]            # Hz, 6 entries


@dataclass
class ButtonMapping:
    index: int                   # table position 1..8 (see usage_tables.R8_BUTTON)
    function: int                # R8_FUNCTION value (Mouse_Enum ordinal)
    macro_enabled: int


@dataclass
class MacroRecord:
    state: int                   # MACRO_* constant
    code: int                    # HID usage (keys) or button index 0..4 (mouse)
    delay_ms: int                # delay after the event (device default 10)

    def pack(self) -> bytes:
        return struct.pack("<BHH", self.state, self.code, self.delay_ms)

    @classmethod
    def unpack(cls, b: bytes) -> "MacroRecord":
        s, c, t = struct.unpack("<BHH", b[:5])
        return cls(s, c, t)


@dataclass
class Macro:
    button: int                  # physical button index the macro belongs to
    name: str = ""
    cycles: int = 1              # 0xFFFF = repeat while held / infinite
    interval_ms: int = 0
    slot: int = 1                # 1..4 ("num" in the official app)
    records: List[MacroRecord] = field(default_factory=list)


@dataclass
class MouseConfig:
    profile_name: str
    left_hand: int
    lod: int
    wheel_speed: int
    wheel_direction: int
    buttons: List[ButtonMapping]
    dpi_x: DpiTable
    dpi_y: DpiTable
    dpi_index: int
    rate: RateTable
    macros: List[Macro]


def find_device() -> Optional[HidrawInfo]:
    for info in enumerate_hidraw(vid=VID, pid=PID):
        if info.usage_page == CONFIG_USAGE_PAGE:
            return info
    return None


def _u16(b: bytes, off: int) -> int:
    return b[off] | (b[off + 1] << 8)


def _utf16be(b: bytes) -> str:
    # strings are stored UTF-16 big-endian, zero terminated
    out = []
    for i in range(0, len(b) - 1, 2):
        if b[i] == 0 and b[i + 1] == 0:
            break
        out.append(chr((b[i] << 8) | b[i + 1]))
    return "".join(out)


def _to_utf16be(s: str, max_bytes: int) -> bytes:
    return s.encode("utf-16-be")[:max_bytes]


class R8Mouse:
    def __init__(self, dev: HidrawDevice, retries: int = 3, timeout: float = 0.5):
        self.dev = dev
        self.retries = retries
        self.timeout = timeout

    @classmethod
    def open(cls, node: Optional[str] = None) -> "R8Mouse":
        if node is None:
            info = find_device()
            if info is None:
                raise R8Error("Retro R8 mouse (2dc8:5205) config interface not found")
            node = info.node
        return cls(HidrawDevice(node))

    def close(self) -> None:
        self.dev.close()

    def __enter__(self) -> "R8Mouse":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ core
    def xfer(self, cls_: int, cmd: int, op: int, payload: bytes = b"") -> bytes:
        """Send one request and return the reply payload (60 bytes)."""
        if len(payload) > 60:
            raise ValueError("payload too long")
        pkt = bytes([0x01, cls_, cmd, op]) + bytes(payload)
        pkt += bytes(64 - len(pkt))
        last = None
        for _ in range(self.retries):
            self.dev.drain(0.0)
            self.dev.write(0, pkt)
            rep = wait_for_reply(
                self.dev,
                lambda r: len(r) >= 4 and r[0] == 0x21 and r[1] == cls_ and r[2] == cmd and (r[3] & op),
                self.timeout,
            )
            if rep is not None:
                return bytes(rep[4:]) + bytes(max(0, 64 - len(rep)))
            last = rep
        raise R8Error(f"no reply to class {cls_:#x} cmd {cmd:#x} op {op}")

    def read(self, cmd: int, payload: bytes = b"") -> bytes:
        return self.xfer(CLS_CONFIG, cmd, OP_READ, payload)

    def write(self, cmd: int, payload: bytes = b"") -> bytes:
        return self.xfer(CLS_CONFIG, cmd, OP_WRITE, payload)

    # ------------------------------------------------------------------ info
    def version_raw(self) -> bytes:
        return self.xfer(CLS_INFO, 4, OP_READ, b"\x00")

    def version(self) -> str:
        """Firmware version as the official app formats it (payload[8].payload[14])."""
        p = self.version_raw()
        return f"{p[8]}.{p[14]:02d}"

    def color(self) -> Tuple[int, str]:
        p = self.read(CMD_COLOR)
        code = p[3]
        return code, COLOR_NAMES.get(code, "unknown")

    # --------------------------------------------------------------- profile
    def get_profile_name(self) -> str:
        data = b""
        for chunk in range(2):
            hdr = (10 | (chunk << 5)) & 0xFFFF
            p = self.read(CMD_PROFILE_NAME, bytes([0, 0, hdr & 0xFF, hdr >> 8]))
            data += p[4:14]
            if p[2] < 10:
                break
        return _utf16be(data)

    def set_profile_name(self, name: str) -> None:
        # the official app always writes the full 20-byte buffer as two chunks
        raw = _to_utf16be(name, PROFILE_NAME_BYTES).ljust(PROFILE_NAME_BYTES, b"\x00")
        for off in range(0, PROFILE_NAME_BYTES, 10):
            chunk = raw[off:off + 10]
            hdr = (len(chunk) & 0x1F) | (((off // 10) & 0x1F) << 5)
            self.write(CMD_PROFILE_NAME, bytes([0, 0, hdr & 0xFF, hdr >> 8]) + chunk)

    def factory_reset(self) -> None:
        self.write(CMD_FACTORY_RESET)

    # ---------------------------------------------------------- simple values
    def get_left_hand(self) -> int:
        return self.read(CMD_LEFT_HAND)[0]

    def set_left_hand(self, on: bool) -> None:
        self.write(CMD_LEFT_HAND, bytes([1 if on else 0]))

    def get_lod(self) -> int:
        return self.read(CMD_LOD)[0]

    def set_lod(self, mm: int) -> None:
        if mm not in (1, 2):
            raise ValueError("lift-off distance must be 1 or 2 (mm)")
        self.write(CMD_LOD, bytes([mm]))

    def get_wheel_speed(self) -> int:
        return self.read(CMD_WHEEL_SPEED)[0]

    def set_wheel_speed(self, speed: int) -> None:
        if not 0 <= speed <= WHEEL_SPEED_MAX:
            raise ValueError(f"wheel speed must be 0..{WHEEL_SPEED_MAX}")
        self.write(CMD_WHEEL_SPEED, bytes([speed]))

    def get_wheel_direction(self) -> int:
        return self.read(CMD_WHEEL_DIRECTION)[0]

    def set_wheel_direction(self, reversed_: bool) -> None:
        self.write(CMD_WHEEL_DIRECTION, bytes([1 if reversed_ else 0]))

    # ------------------------------------------------------------------- DPI
    def get_dpi(self, axis: int) -> DpiTable:
        p = self.read(CMD_DPI, bytes([axis]))[1:]
        return DpiTable(p[0], [_u16(p, 1 + 2 * i) for i in range(6)])

    def set_dpi(self, axis: int, table: DpiTable) -> None:
        if len(table.values) != 6:
            raise ValueError("need 6 DPI values")
        for v in table.values:
            if not DPI_MIN <= v <= DPI_MAX:
                raise ValueError(f"DPI {v} out of range {DPI_MIN}..{DPI_MAX}")
        payload = bytes([axis, table.enabled_mask & 0x3F]) + b"".join(struct.pack("<H", v) for v in table.values)
        self.write(CMD_DPI, payload)

    def get_dpi_index(self) -> int:
        return self.read(CMD_DPI_INDEX)[1]

    def set_dpi_index(self, index: int, dpi: int) -> None:
        self.write(CMD_DPI_INDEX, bytes([6, index]) + struct.pack("<H", dpi))

    # ----------------------------------------------------------- polling rate
    def get_rate_raw(self) -> bytes:
        return self.read(CMD_RATE)

    def get_rate(self) -> RateTable:
        p = self.get_rate_raw()
        return RateTable(p[0], p[1], [_u16(p, 4 + 2 * i) for i in range(6)])

    def set_rate(self, table: RateTable) -> None:
        payload = bytes([table.count, table.current, 0, 0, 0, 0])
        n = 6 if table.count == 6 else 5
        payload += b"".join(struct.pack("<H", v) for v in table.values[:n])
        self.write(CMD_RATE, payload)

    # --------------------------------------------------------------- buttons
    def get_buttons(self) -> List[ButtonMapping]:
        """The button table, positions 1..8 (0 is the left button, which is not
        remappable).  A button is identified by its table position, which is
        also the index a write (`set_button`) takes; the index byte inside each
        reply entry is informational (positions 5/6 report 9/10 on the R8) except
        that 0xFF marks the end of the table.  Function 255 means disabled."""
        out: List[ButtonMapping] = []
        for start in (1, 3, 5, 7):
            p = self.read(CMD_READ_MAP, bytes([9, start, 2]))[3:]
            for j in range(2):
                e = p[j * 6:(j + 1) * 6]
                if e[1] == 0xFF:
                    return out
                out.append(ButtonMapping(index=start + j, function=struct.unpack("<I", e[2:6])[0], macro_enabled=e[0]))
        return out

    def set_button(self, index: int, function: int, macro_enabled: int = 0) -> None:
        self.write(CMD_WRITE_MAP, bytes([macro_enabled, index]) + struct.pack("<I", function))

    # ---------------------------------------------------------------- macros
    def get_macro_header(self, button: int) -> bytes:
        return self.read(CMD_MACRO, bytes([1, 0, button]))[1:]

    def get_macro_name(self, button: int) -> str:
        data = b""
        for part in (0, 8):
            data += self.read(CMD_MACRO, bytes([4, button, part]))[3:13]
        return _utf16be(data)

    def get_macro_records(self, count: int) -> List[MacroRecord]:
        recs: List[MacroRecord] = []
        start = 0
        while start < count:
            n = min(2, count - start)
            p = self.read(CMD_MACRO, bytes([2, 0, 0, start, n]))[5:15]
            for i in range(n):
                recs.append(MacroRecord.unpack(p[i * 5:(i + 1) * 5]))
            start += 2
        return recs

    def get_macro(self, button: int) -> Macro:
        h = self.get_macro_header(button)
        count = h[0]
        m = Macro(button=button, cycles=_u16(h, 2), interval_ms=_u16(h, 8), slot=h[4])
        m.name = self.get_macro_name(button)
        m.records = self.get_macro_records(count) if count else []
        return m

    def set_macro(self, macro: Macro) -> None:
        count = len(macro.records)
        if count == 0 or count > MACRO_MAX_RECORDS:
            raise ValueError(f"macro needs 1..{MACRO_MAX_RECORDS} records")
        hdr = bytes([1, count, macro.button]) + struct.pack("<H", macro.cycles) + bytes([macro.slot, 0, 0, 0x20]) + struct.pack("<H", macro.interval_ms)
        self.write(CMD_MACRO, hdr)
        raw_name = _to_utf16be(macro.name, MACRO_NAME_BYTES).ljust(MACRO_NAME_BYTES, b"\x00")
        for off, part in ((0, 0), (10, 8), (20, 0x10)):
            self.write(CMD_MACRO, bytes([4, macro.button, part]) + raw_name[off:off + 10])
        data = b"".join(r.pack() for r in macro.records)
        checksum = sum(data) & 0xFFFF
        off = 0
        while off < len(data):
            chunk = data[off:off + 10]
            last = off + len(chunk) >= len(data)
            head = bytes([3, checksum & 0xFF, checksum >> 8]) if last else bytes([2, 0, 0])
            head += bytes([off // 5, len(chunk) // 5])
            self.write(CMD_MACRO, head + chunk)
            off += len(chunk)

    def assign_macro(self, macro: Macro, function: Optional[int] = None) -> None:
        """Store a macro and switch it on for its button.

        Order matters on the R8 (firmware 10.14): the button entry must be written
        with `macro_enable = 1` *before* the macro header/name/data, which is what
        the official app does (`WriteMapKey`, 100 ms pause, `WriteMouseMacro`).
        Writing the macro first and enabling afterwards leaves the flag at 0.
        `function` is the button's normal function to keep; by default the current
        one is read back and reused."""
        if function is None:
            function = {b.index: b for b in self.get_buttons()}[macro.button].function
        self.set_button(macro.button, function, 1)
        time.sleep(0.1)
        self.set_macro(macro)

    # ------------------------------------------------------------- full dump
    def read_config(self) -> MouseConfig:
        buttons = self.get_buttons()
        macros = []
        for b in buttons:
            if b.macro_enabled == 1 and b.index in MACRO_SLOT:
                try:
                    macros.append(self.get_macro(b.index))
                except R8Error:
                    pass
        return MouseConfig(
            profile_name=self.get_profile_name(),
            left_hand=self.get_left_hand(),
            lod=self.get_lod(),
            wheel_speed=self.get_wheel_speed(),
            wheel_direction=self.get_wheel_direction(),
            buttons=buttons,
            dpi_x=self.get_dpi(0),
            dpi_y=self.get_dpi(1),
            dpi_index=self.get_dpi_index(),
            rate=self.get_rate(),
            macros=macros,
        )
