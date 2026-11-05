# 8BitDo Retro 87 / Retro R8 configuration protocol

Derived from 8BitDo Ultimate Software V2 for Windows (v1.35): the managed
UI (`8BitDo Ultimate Software V2.dll`, decompiled with ilspycmd) and the native
`8BitDoAdvance.dll` (decompiled with Ghidra) which builds the actual HID
packets. Everything below was verified against real hardware.

Vendor ID is `0x2DC8` for both devices. The official app refers to the
keyboard as "JP" and to the mouse as "Mouse"/"Retro R8".

## Retro 87 keyboard (PID 0x5200 wired, 0x5201 via 2.4 GHz receiver)

Three USB HID interfaces:

| iface | usage page/usage | purpose |
|-------|------------------|---------|
| 0 | 0x01/0x02 (mouse), report ID 3 | mouse reports used when a key is remapped to a mouse action |
| 1 | 0x01/0x06 keyboard (+ consumer, system, NKRO) | normal typing |
| 2 | 0x8C/0x01 | **configuration** |

Interface 2 report IDs: out `0x52` (config request), `0xB2` (bootloader
jump, used by the DFU tool), `0x51`; in `0x54` (config reply), `0xB1`.

### Framing

Request: output report `0x52`, 32 bytes, `payload[0]` = command.
Reply: input report `0x54`, 32 bytes, `payload[0]` echoes the command.
Writes are acknowledged by a reply `E4 08 ...`.

### Commands

| cmd | dir | payload |
|-----|-----|---------|
| `0x89` | read | volume: reply `[89, level]` (1..5) |
| `0x79` | write | `[79, level]` -> ack |
| `0x88` | read | "special feature" flags: reply `[88, flags]` |
| `0x78` | write | `[78, flags]` -> ack |
| `0x80` | read | profile name, chunked: reply `[80, ?, more, 29 bytes]`, 61 bytes total, UTF-16BE, zero terminated |
| `0x70` | write | profile name: `[70, chunk_len, more, 29 bytes]` per chunk, then one ack. `[70, 0, 0]` (empty name) is the app's **factory reset** |
| `0x81` | read | list of remapped keys, chunked: reply `[81, 30 bytes, more]`; data = pairs `(key, x)` until `key == 0`, max 192 bytes |
| `0x83` | read | mapping of one key: `[83, key]` -> `[83, key, type, value...]` |
| `0xFA` | write | set mapping: `FA 03 0C 00 AA 09 71 <key> <type> <value...>` -> ack |
| `0x82` | read | list of keys that have macros: reply `[82, 28 bytes, more]`, 32 bytes total, 4-byte entries until key 0 |
| `0x84` | read | macro name: `[84, key]` -> reply `[84, ?, ?, more, 28 bytes]`, 61 bytes UTF-16BE |
| `0x74` | write | macro name: `[74, key, chunk_len, more, 28 bytes]` per chunk, then ack |
| `0x86` | read | macro data: `[86, key]` -> reply `[86, ?, more, ?, ?, ?, 26 bytes]`, 609 bytes total |
| `0x76` | write | macro data (see below) -> ack. `[76, FF]` is sent by the app before reading ("switch report") |
| `0x77` | write | clear macro: `[77, key, record_count]` -> ack |
| `0x7B` | write | "switch report extra": `[7B, value]` -> ack |

Key index = USB HID keyboard usage of the physical key (A = 4 ...
right GUI = 0xE7). Extra indices: Super Button A = 109, B = 108,
K1..K8 = 116,117,114,115,112,113,110,111.

Mapping types / values:

- `7` keyboard: `[modifier, usage, 0, 0]`; modifier is a HID usage 0xE0..0xE7
  or 0; `[0, 3, 0, 0]` = Fn; all zero = key disabled. Mapping a key to itself
  removes it from the remap list.
- `12` consumer: `[usage_lo, usage_hi, 0, 0]` (0xEA vol-, 0xE9 vol+, 0xE2 mute,
  0xCD play/pause, 0xB6 prev, 0xB5 next, 0x18A mail, 0x192 calculator,
  0x223 browser home, 0x70/0x6F brightness; the app sends 0x08E3 for "Computer").
- `1` mouse: 5-byte mouse report `[buttons, x, y, wheel, pan]`
  (buttons 1 left, 2 right, 4 middle, 8 forward, 16 back, 128 double click;
  wheel/pan +2 / -2 (0xFE) for scroll).

Macro data (`0x86` read / `0x76` write) is a byte blob:
`[1, cycles, flag, count, records..., (0F ms_lo ms_hi 00)]` where `flag = 0x20`
means repeat while held (cycles 255), `count` = number of 3-byte records,
records are `[0x81, usage, 0]` key down, `[0x01, usage, 0]` key up,
`[0x83/0x03, usage, 0]` modifier down/up, `[0x0F, ms_lo, ms_hi]` delay.
The repeat interval is appended as a trailing delay record (4 bytes, the
last byte 0), and `count` includes it.

`0x76` write packets: `[76, key, more, offset_lo, offset_hi, len, 26 bytes]`.
If the blob is < 22 bytes: one packet (`len` = 26, more = 0). Otherwise the
first packet carries 21 blob bytes (`len` 25, more 1), following packets
carry 24 bytes each with `offset = sent + 4`, and the last has more = 0.
A single ack follows the last packet.

The firmware version is not readable through this interface (the official
app runs `dfu4.exe -r -dv 2dc8 -dp 5200`); USB `bcdDevice` is shown instead.

## Retro R8 mouse (PID 0x5205 wired, 0x5206 via receiver)

Four USB HID interfaces:

| iface | usage page/usage | purpose |
|-------|------------------|---------|
| 0 | 0x01/0x02 | mouse (16-bit X/Y) |
| 1 | 0x01/0x06 | keyboard (used for key functions on buttons) |
| 2 | 0xFF00/0x01, 64-byte in/out, no report ID | **configuration** |
| 3 | 0xFF0B/0x0104 | Realtek HID DFU (firmware update) |

Input reports, useful when checking what a button does (`tools/reverse/hid_capture.py`):
iface 0 sends `[1, buttons, x lo, x hi, y lo, y hi, wheel, pan]` (buttons 1 left,
2 right, 4 middle, 8 forward, 16 back; wheel +1 = away from the user / scroll up,
pan -1 = left), iface 1 a standard keyboard report `[1, modifiers, 0, usage x6]`
(usage range 0..0xFF; report 2 is consumer, report 6 system control). Key
functions arrive there as plain usages, e.g. function 247 (`f19`) sends 0x6E and
252 (`f24`) 0x73 (seen on hardware). The 5206 adapter's iface 1 has the same layout.

### Framing

Request (64 bytes): `[0x01, class, cmd, op, payload...]`, op `1` = read,
`4` = write. Reply: `[0x21, class, cmd, status, payload...]` where
`status & op != 0` on success (`0x11` / `0x14`). Class `6` is configuration,
class `4` device info.

### Commands (class 6 unless noted)

| cmd | read payload -> reply payload | write payload |
|-----|------------------------------|---------------|
| class 4 `0x04` | `[0]` -> version info; app shows `payload[8].payload[14]` | - |
| `0x25` | color/edition: `payload[3]` (0 Xbox, 1 N, 3 C64, 7 Forest, 8 GoW) | - |
| `0x1C` | profile name: `[0,0,hdr_lo,hdr_hi]`, `hdr = 10 | chunk<<5` -> `[.., len, .., 10 bytes at 4]` | same header with `len | chunk<<5` + 10 bytes; always 2 chunks (20 bytes UTF-16BE) |
| `0x27` | left-hand mode `[v]` | `[0/1]` |
| `0x26` | lift-off distance `[mm]` | `[1|2]` |
| `0x24` | wheel speed `[v]` | `[0..14]` |
| `0x23` | wheel direction `[v]` | `[0/1]` |
| `0x28` | DPI: `[axis]` -> `[axis, enable_mask, 6 x u16 LE]` | `[axis, enable_mask, 6 x u16]` (50..26000) |
| `0x12` | active DPI slot: -> `[?, index]` | `[6, index, dpi u16]` |
| `0x0D` | polling rate: -> `[count, current, 0, 0, 6 x u16 at offset 4]` | `[count, current, 0,0,0,0, 6 x u16 at offset 6]` (this is what the official DLL sends) |
| `0x14` | button map: `[9, first_index, 2]` -> `[.., .., .., 2 x (macro_en, index, u32 function)]` | - |
| `0x10` | - | `[macro_enable, index, u32 function LE]` |
| `0x0F` | macros, see below | |
| `0x33` | - | factory reset (no payload) |

Button indices (= table positions, and the index a `0x10` write takes): 0 left,
1 right, 2 middle, 3/4 thumb-side buttons (forward/back by default; 3 is the
one the owner calls top-left, 4 bottom-left, identified by pressing each), 5/6 the
pair on the other side (the app's "R4"/"R5"; function 255 = disabled from the
factory, so they do nothing until mapped), 7 the wheel rolled towards the user
(function 32 by default), 8 the wheel rolled away (33 by default); both are
remappable like a button. Note that the app's `Mouse_Enum` names 32 `WHEEL_UP`
and 33 `WHEEL_DOWN`, but 32 sends HID wheel -1 (scroll down) and 33 wheel +1,
so `usage_tables` calls them `scroll_down` / `scroll_up`. The table on the R8
(firmware 10.14) has 8 entries; position 9 reads back with index byte 255 (end
marker). The index byte inside each reply entry is informational: positions
5/6 report 9/10, the others their own position. The official app (v1.35) reads
positions 1..6 only, so it never shows the wheel entries. Which entry drives
which input was confirmed by mapping test functions and capturing the mouse's
HID reports while pressing the buttons (firmware 10.14, `wheel direction` 0):

| entry | test function written | input pressed | report seen |
|-------|-----------------------|---------------|-------------|
| 5 | 34 scroll left | front right-side button | iface 0, pan -1 |
| 6 | 35 scroll right | back right-side button | iface 0, pan +1 |
| 7 | 241 F13 | wheel rolled towards the user | iface 1, usage 0x68 |
| 8 | 242 F14 | wheel rolled away | iface 1, usage 0x69 |
| 5 | 32 (app: "wheel up") | front right-side button | iface 0, wheel -1 (down) |

Function values
are the ordinals of the app's `Mouse_Enum` (1 left click, 2 right, 3 middle,
4 back, 5 forward, 7 play/pause, 24 DPI+, 26 DPI cycle, 32..35 scroll
(down, up, left, right - see above),
128.. keyboard keys, ...) - see `usage_tables.R8_FUNCTION`.

Macro sub-commands (cmd `0x0F`, payload byte 0 selects):

- `1` header: write `[1, count, button, cycles u16, slot, 0, 0, 0x20, interval_ms u16]`;
  read `[1, 0, button]` -> the same layout from payload byte 1.
- `4` name: `[4, button, part]` + 10 bytes, part 0 / 8 / 0x10 (30 bytes UTF-16BE).
- `2`/`3` data: records are `[state, code u16, delay_ms u16]` (state 10 key
  press, 2 key release, 15 mouse press, 7 mouse release; code = HID usage
  with an optional modifier usage in the high byte, or mouse button 0 left,
  1 right, 2 middle, 4 back, 3 forward). Written in 10-byte chunks
  `[2, 0, 0, first_record, n_records, data]`, the last chunk as
  `[3, sum_lo, sum_hi, first_record, n_records, data]` with a 16-bit byte sum
  of the whole blob. Read: `[2, 0, 0, first_record, n(<=2)]` -> data at payload byte 5.
- A macro is active when the button's `macro_enable` is 1 (`0x10`); the
  button keeps its normal function value. `cycles = 0xFFFF` is the app's "Repeated"
  mode: the macro loops until another mouse button is pressed (verified on firmware
  10.14, it does *not* stop on release). There is no while-held macro mode: the
  native `WriteMacroStart` hardcodes header byte 7 to `0x20` (the same "infinite"
  flag the keyboard's `writeMacroJP` sets when cycles is 255), so the app can only
  express once / N times / loop. The button function `fire` (38, `KEY_CFG_FIRE`)
  is a single click on this firmware, not a rapid-fire.
- Write order matters (verified on firmware 10.14): the `0x10` entry with
  `macro_enable = 1` must go out *before* the macro header / name / data, which is
  the app's sequence (`WriteMapKey`, 100 ms pause, then `WriteMouseMacro`). Sent the
  other way round, or the `0x10` write alone, the flag reads back as 0 and the
  button keeps its plain function. `R8Mouse.assign_macro` does it in the right order.
