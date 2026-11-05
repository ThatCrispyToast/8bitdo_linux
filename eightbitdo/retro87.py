"""8BitDo Retro 87 Mechanical Keyboard (USB 2dc8:5200) configuration protocol.

Reverse-engineered from 8BitDo Ultimate Software V2 (8BitDoAdvance.dll).

Transport: the third HID interface (usage page 0x8C).  Requests are 32-byte
output reports with report ID 0x52, replies are 32-byte input reports with
report ID 0x54.  The first payload byte is a command; replies echo it.
Writes are acknowledged with a reply starting ``E4 08``.
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .hidraw import HidrawDevice, HidrawInfo, enumerate_hidraw, wait_for_reply

VID = 0x2DC8
PIDS = (0x5200, 0x5201)          # wired / 2.4 GHz receiver ("JP" / "JPUSB")
CONFIG_USAGE_PAGE = 0x8C
REPORT_OUT = 0x52
REPORT_IN = 0x54
PAYLOAD = 32

# commands
CMD_SET_NAME = 0x70
CMD_SET_MACRO_NAME = 0x74
CMD_SET_MACRO = 0x76             # also used as "switch report" with key 0xFF
CMD_CLEAR_MACRO = 0x77
CMD_SET_FEATURE = 0x78
CMD_SET_VOLUME = 0x79
CMD_SWITCH_REPORT_EXTRA = 0x7B
CMD_GET_NAME = 0x80
CMD_GET_MAPPED_KEYS = 0x81
CMD_GET_MACRO_KEYS = 0x82
CMD_GET_MAPPING = 0x83
CMD_GET_MACRO_NAME = 0x84
CMD_GET_MACRO = 0x86
CMD_GET_FEATURE = 0x88
CMD_GET_VOLUME = 0x89
CMD_SET_MAPPING = 0xFA           # wrapped: FA 03 0C 00 AA 09 71 <key> <type> <value...>
ACK = (0xE4, 0x08)
REPORT_KEY_EVENT = 0x07          # unsolicited: key press report while listening

# mapping value types (byte after the key index in the SET_MAPPING packet)
MAP_KEYBOARD = 7                 # value = [modifier, usage, 0, 0]
MAP_CONSUMER = 12                # value = [usage_lo, usage_hi, 0, 0]
MAP_MOUSE = 1                    # value = [buttons, x, y, wheel, pan]

NAME_BYTES = 61                  # UTF-16BE, zero terminated (30 chars)
MACRO_NAME_BYTES = 61
MACRO_MAX_RECORDS = 200
MACRO_BYTES = 609

# macro record types (3-byte records: [type, code, 0] or [0x0F, ms_lo, ms_hi])
REC_KEY_DOWN = 0x81
REC_KEY_UP = 0x01
REC_MOD_DOWN = 0x83
REC_MOD_UP = 0x03
REC_DELAY = 0x0F
MACRO_INFINITE = 0xFF

# extra physical key indices used by the official app (besides HID usages)
EXTRA_KEYS = {
    "super_a": 109, "super_b": 108,
    "k1": 116, "k2": 117, "k3": 114, "k4": 115, "k5": 112, "k6": 113, "k7": 110, "k8": 111,
}
EXTRA_KEY_NAMES = {v: k for k, v in EXTRA_KEYS.items()}


class Retro87Error(RuntimeError):
    pass


@dataclass
class KeyMapping:
    key: int                     # physical key index (HID usage or EXTRA_KEYS)
    kind: int                    # MAP_KEYBOARD / MAP_CONSUMER / MAP_MOUSE
    value: bytes                 # 4 or 5 bytes


@dataclass
class MacroRecord:
    type: int                    # REC_* constant
    code: int                    # HID usage, or delay in ms for REC_DELAY

    def pack(self) -> bytes:
        if self.type == REC_DELAY:
            return bytes([REC_DELAY, self.code & 0xFF, (self.code >> 8) & 0xFF])
        return bytes([self.type, self.code & 0xFF, 0])

    @classmethod
    def unpack(cls, b: bytes) -> "MacroRecord":
        if b[0] == REC_DELAY:
            return cls(REC_DELAY, b[1] | (b[2] << 8))
        return cls(b[0], b[1])


@dataclass
class KeyMacro:
    key: int
    name: str = ""
    cycles: int = 1              # MACRO_INFINITE (255) = loop while held
    interval_ms: int = 0
    records: List[MacroRecord] = field(default_factory=list)


@dataclass
class KeyboardConfig:
    profile_name: str
    volume: int
    feature: int
    mappings: List[KeyMapping]
    macros: List[KeyMacro]


def find_device() -> Optional[HidrawInfo]:
    for info in enumerate_hidraw(vid=VID):
        if info.pid in PIDS and info.usage_page == CONFIG_USAGE_PAGE:
            return info
    return None


def _utf16be(b: bytes) -> str:
    out = []
    for i in range(0, len(b) - 1, 2):
        if b[i] == 0 and b[i + 1] == 0:
            break
        out.append(chr((b[i] << 8) | b[i + 1]))
    return "".join(out)


def _to_utf16be(s: str, max_bytes: int) -> bytes:
    return s.encode("utf-16-be")[: max_bytes - (max_bytes % 2)]


class Retro87:
    def __init__(self, dev: HidrawDevice, timeout: float = 0.5):
        self.dev = dev
        self.timeout = timeout

    @classmethod
    def open(cls, node: Optional[str] = None) -> "Retro87":
        if node is None:
            info = find_device()
            if info is None:
                raise Retro87Error("Retro 87 keyboard (2dc8:5200) config interface not found")
            node = info.node
        return cls(HidrawDevice(node))

    def close(self) -> None:
        self.dev.close()

    def __enter__(self) -> "Retro87":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ core
    def _send(self, payload: bytes) -> None:
        if len(payload) > PAYLOAD:
            raise ValueError("payload too long")
        self.dev.write(REPORT_OUT, bytes(payload) + bytes(PAYLOAD - len(payload)))

    def _wait(self, pred: Callable[[bytes], bool], timeout: Optional[float] = None) -> Optional[bytes]:
        rep = wait_for_reply(self.dev, lambda r: len(r) >= 3 and r[0] == REPORT_IN and pred(r[1:]), timeout or self.timeout)
        return None if rep is None else bytes(rep[1:]) + bytes(max(0, PAYLOAD - len(rep) + 1))

    def _wait_ack(self, timeout: Optional[float] = None) -> bool:
        return self._wait(lambda p: p[0] == ACK[0] and p[1] == ACK[1], timeout) is not None

    def _query(self, payload: bytes, expect: Optional[int] = None, retries: int = 3) -> bytes:
        """Send a request and return the first reply whose command byte matches."""
        exp = payload[0] if expect is None else expect
        for _ in range(retries):
            self.dev.drain(0.0)
            self._send(payload)
            rep = self._wait(lambda p: p[0] == exp)
            if rep is not None:
                return rep
        raise Retro87Error(f"no reply to command {payload[0]:#04x}")

    def _next_chunk(self, expect: int, timeout: float = 0.5) -> bytes:
        rep = self._wait(lambda p: p[0] == expect, timeout)
        if rep is None:
            raise Retro87Error(f"timeout waiting for chunk of command {expect:#04x}")
        return rep

    def _write(self, payload: bytes, retries: int = 2, timeout: float = 1.0) -> None:
        for _ in range(retries):
            self.dev.drain(0.0)
            self._send(payload)
            if self._wait_ack(timeout):
                return
        raise Retro87Error(f"command {payload[0]:#04x} was not acknowledged")

    # ------------------------------------------------------------- settings
    def get_volume(self) -> int:
        return self._query(bytes([CMD_GET_VOLUME]))[1]

    def set_volume(self, level: int) -> None:
        if not 1 <= level <= 5:
            raise ValueError("volume level must be 1..5")
        self._write(bytes([CMD_SET_VOLUME, level]))

    def get_feature(self) -> int:
        return self._query(bytes([CMD_GET_FEATURE]))[1]

    def set_feature(self, value: int) -> None:
        self._write(bytes([CMD_SET_FEATURE, value & 0xFF]))

    def switch_report(self, value: int = 0xFF) -> None:
        """What the official app sends before reading the configuration."""
        self._write(bytes([CMD_SET_MACRO, value & 0xFF]))

    def switch_report_extra(self, value: int) -> None:
        self._write(bytes([CMD_SWITCH_REPORT_EXTRA, value & 0xFF]))

    # ---------------------------------------------------------- profile name
    def get_profile_name(self) -> str:
        data = b""
        rep = self._query(bytes([CMD_GET_NAME]))
        while True:
            data += rep[3:32]
            if rep[2] != 1 or len(data) >= NAME_BYTES:
                break
            rep = self._next_chunk(CMD_GET_NAME)
        return _utf16be(data[:NAME_BYTES])

    def set_profile_name(self, name: str) -> None:
        raw = _to_utf16be(name, NAME_BYTES - 1)
        self._send_name_chunks(CMD_SET_NAME, raw, 29, extra=b"")

    def _send_name_chunks(self, cmd: int, raw: bytes, chunk: int, extra: bytes) -> None:
        """Shared by profile name (0x70) and macro name (0x74)."""
        total = len(raw)
        off = 0
        first = True
        while first or off < total:
            first = False
            part = raw[off:off + chunk]
            more = 1 if off + chunk < total else 0
            self._send(bytes([cmd]) + extra + bytes([len(part), more]) + part.ljust(chunk, b"\x00"))
            off += chunk
            if more:
                time.sleep(0.01)
        if not self._wait_ack(1.0):
            raise Retro87Error("name write was not acknowledged")

    def reset(self) -> None:
        """Factory reset: what the official app's Reset button does (empty name)."""
        self._write(bytes([CMD_SET_NAME]))

    # ---------------------------------------------------------- key mapping
    def get_mapped_keys(self) -> List[int]:
        data = b""
        rep = self._query(bytes([CMD_GET_MAPPED_KEYS]))
        while True:
            data += rep[1:31]
            if rep[31] == 0 or len(data) >= 192:
                break
            rep = self._next_chunk(CMD_GET_MAPPED_KEYS)
        keys = []
        for i in range(0, len(data) - 1, 2):
            if data[i] == 0:
                break
            keys.append(data[i])
        return keys

    def get_mapping(self, key: int) -> KeyMapping:
        rep = self._query(bytes([CMD_GET_MAPPING, key]))
        # reply: [0x83, key, type, value...]
        kind = rep[2]
        n = 5 if kind == MAP_MOUSE else 4
        return KeyMapping(key=key, kind=kind, value=bytes(rep[3:3 + n]))

    def set_mapping(self, key: int, kind: int, value: bytes) -> None:
        if kind == MAP_MOUSE:
            value = bytes(value)[:5].ljust(5, b"\x00")
        else:
            value = bytes(value)[:4].ljust(4, b"\x00")
        pkt = bytes([CMD_SET_MAPPING, 0x03, 0x0C, 0x00, 0xAA, 0x09, 0x71, key & 0xFF, kind]) + value
        self._write(pkt)

    def map_key(self, key: int, usage: int, modifier: int = 0) -> None:
        self.set_mapping(key, MAP_KEYBOARD, bytes([modifier, usage, 0, 0]))

    def map_consumer(self, key: int, usage: int) -> None:
        self.set_mapping(key, MAP_CONSUMER, bytes([usage & 0xFF, usage >> 8, 0, 0]))

    def map_mouse(self, key: int, report: bytes) -> None:
        self.set_mapping(key, MAP_MOUSE, report)

    def unmap(self, key: int) -> None:
        """Restore a key to itself (how the official app reverts a remap)."""
        if key in EXTRA_KEY_NAMES:
            self.set_mapping(key, MAP_KEYBOARD, bytes(4))
        else:
            self.map_key(key, key)

    # ---------------------------------------------------------------- macros
    def get_macro_keys(self) -> List[int]:
        data = b""
        rep = self._query(bytes([CMD_GET_MACRO_KEYS]))
        while True:
            data += rep[1:29] if len(data) < 28 else rep[1:5]
            if rep[29] == 0 or len(data) >= 32:
                break
            rep = self._next_chunk(CMD_GET_MACRO_KEYS)
        keys = []
        for i in range(0, 32, 4):
            if i >= len(data) or data[i] == 0:
                break
            keys.append(data[i])
        return keys

    def get_macro_name(self, key: int) -> str:
        data = b""
        rep = self._query(bytes([CMD_GET_MACRO_NAME, key]))
        while True:
            data += rep[4:32]
            if rep[3] == 0 or len(data) >= MACRO_NAME_BYTES:
                break
            rep = self._next_chunk(CMD_GET_MACRO_NAME)
        return _utf16be(data[:MACRO_NAME_BYTES])

    def get_macro_raw(self, key: int) -> bytes:
        data = b""
        rep = self._query(bytes([CMD_GET_MACRO, key]))
        while True:
            data += rep[6:32]
            if rep[2] == 0 or len(data) >= MACRO_BYTES:
                break
            rep = self._next_chunk(CMD_GET_MACRO)
        return data[:MACRO_BYTES]

    def get_macro(self, key: int) -> KeyMacro:
        raw = self.get_macro_raw(key)
        m = KeyMacro(key=key, name=self.get_macro_name(key))
        m.cycles = MACRO_INFINITE if raw[2] == 0x20 else raw[1]
        count = raw[3]
        recs = [MacroRecord.unpack(raw[4 + 3 * i: 7 + 3 * i]) for i in range(count)]
        # the official app stores the repeat interval as a trailing delay record
        if recs and recs[-1].type == REC_DELAY and (m.cycles > 1 or len(recs) > 1):
            m.interval_ms = recs[-1].code
            recs = recs[:-1]
        m.records = recs
        return m

    def set_macro_name(self, key: int, name: str) -> None:
        raw = _to_utf16be(name, MACRO_NAME_BYTES - 1)
        self._send_name_chunks(CMD_SET_MACRO_NAME, raw, 28, extra=bytes([key & 0xFF]))

    def set_macro(self, macro: KeyMacro) -> None:
        if not macro.records or len(macro.records) > MACRO_MAX_RECORDS:
            raise ValueError(f"macro needs 1..{MACRO_MAX_RECORDS} records")
        self.set_macro_name(macro.key, macro.name or "macro")
        data = b"".join(r.pack() for r in macro.records)
        if macro.interval_ms > 0 or macro.cycles > 1:
            data += bytes([REC_DELAY, macro.interval_ms & 0xFF, (macro.interval_ms >> 8) & 0xFF, 0])[:4]
        header = bytearray([1, 0, 0, len(data) // 3])
        if macro.cycles == MACRO_INFINITE:
            header[2] = 0x20
        else:
            header[1] = macro.cycles & 0xFF
        key = macro.key & 0xFF
        # packet: [0x76, key, more, offset_lo, offset_hi, len, payload(26)]
        if len(data) < 22:
            payload = bytes(header) + data
            self._send(bytes([CMD_SET_MACRO, key, 0, 0, 0, 26]) + payload.ljust(26, b"\x00"))
        else:
            payload = bytes(header) + data[:21]
            self._send(bytes([CMD_SET_MACRO, key, 1, 0, 0, 25]) + payload.ljust(26, b"\x00"))
            sent = 21
            while sent < len(data):
                remaining = len(data) - sent
                offset = sent + 4
                if remaining < 25:
                    part = data[sent:]
                    more = 0
                else:
                    part = data[sent:sent + 24]
                    more = 1
                time.sleep(0.01)
                self._send(bytes([CMD_SET_MACRO, key, more, offset & 0xFF, offset >> 8, len(part)]) + part.ljust(26, b"\x00"))
                sent += len(part)
        if not self._wait_ack(4.0):
            raise Retro87Error("macro write was not acknowledged")

    def clear_macro(self, key: int, count: int = 0) -> None:
        self._write(bytes([CMD_CLEAR_MACRO, key & 0xFF, count & 0xFF]))

    # ---------------------------------------------------------------- misc
    def listen(self, seconds: float):
        """Yield raw vendor input payloads for `seconds` (key-event reports have type 7)."""
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            rep = self.dev.read(remaining)
            if rep is not None and rep[0] == REPORT_IN:
                yield bytes(rep[1:])

    def read_config(self) -> KeyboardConfig:
        mappings = [self.get_mapping(k) for k in self.get_mapped_keys()]
        macros = []
        for k in self.get_macro_keys():
            try:
                macros.append(self.get_macro(k))
            except Retro87Error:
                pass
        return KeyboardConfig(
            profile_name=self.get_profile_name(),
            volume=self.get_volume(),
            feature=self.get_feature(),
            mappings=mappings,
            macros=macros,
        )
