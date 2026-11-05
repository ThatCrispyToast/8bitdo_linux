"""Command line interface: ``8bitdo-cfg``."""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

from . import hidraw, r8mouse, retro87, usage_tables as ut


class CliError(Exception):
    pass


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    raise CliError(msg)


def _onoff(s: str) -> bool:
    v = s.strip().lower()
    if v in ("on", "1", "true", "yes", "reversed", "left"):
        return True
    if v in ("off", "0", "false", "no", "normal", "right"):
        return False
    _die(f"expected on/off, got {s!r}")


def _asdict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (bytes, bytearray)):
        return list(obj)
    if isinstance(obj, list):
        return [_asdict(x) for x in obj]
    return obj


# ----------------------------------------------------------------------------
# keyboard: mapping targets and macro steps
# ----------------------------------------------------------------------------
def parse_kb_target(text: str) -> Tuple[int, bytes]:
    """Parse a remap target into (kind, value) for Retro87.set_mapping."""
    t = text.strip().lower()
    if t in ("fn",):
        return retro87.MAP_KEYBOARD, bytes([0, 3, 0, 0])
    if t in ("none", "disabled", "disable", "off"):
        return retro87.MAP_KEYBOARD, bytes(4)
    if t.startswith("consumer:") or t.startswith("media:"):
        name = t.split(":", 1)[1]
        name = ut.CONSUMER_ALIASES.get(name, name)
        if name not in ut.CONSUMER:
            _die(f"unknown media function {name!r}; see 'keyboard targets'")
        u = ut.CONSUMER[name]
        return retro87.MAP_CONSUMER, bytes([u & 0xFF, u >> 8, 0, 0])
    if t.startswith("mouse:"):
        name = t.split(":", 1)[1]
        if not name.startswith(("mouse_", "scroll_")):
            name = "mouse_" + name
        if name not in ut.MOUSE_ACTION:
            _die(f"unknown mouse action {name!r}; see 'keyboard targets'")
        return retro87.MAP_MOUSE, ut.MOUSE_ACTION[name]
    # bare media / mouse names are accepted too
    n = ut.CONSUMER_ALIASES.get(t, t)
    if n in ut.CONSUMER and ut.key_code(t) is None:
        u = ut.CONSUMER[n]
        return retro87.MAP_CONSUMER, bytes([u & 0xFF, u >> 8, 0, 0])
    if t in ut.MOUSE_ACTION:
        return retro87.MAP_MOUSE, ut.MOUSE_ACTION[t]
    # modifier+key or key
    mod = 0
    if "+" in t:
        mod_name, t = t.rsplit("+", 1)
        mc = ut.key_code(mod_name)
        if mc is None or mc not in ut.MODIFIER_CODES:
            _die(f"{mod_name!r} is not a modifier (use ctrl/shift/alt/gui, optionally left_/right_)")
        mod = mc
    code = ut.key_code(t)
    if code is None:
        _die(f"unknown key {t!r}; see 'keyboard keys'")
    return retro87.MAP_KEYBOARD, bytes([mod, code, 0, 0])


def format_kb_mapping(m: retro87.KeyMapping) -> str:
    v = m.value
    if m.kind == retro87.MAP_KEYBOARD:
        if v[1] == 3 and v[0] == 0:
            return "fn"
        if v[0] == 0 and v[1] == 0:
            return "none"
        name = ut.key_name(v[1]) if v[1] else ""
        if v[0] and v[1]:
            return f"{ut.key_name(v[0])}+{name}"
        if v[0]:
            return ut.key_name(v[0])
        return name
    if m.kind == retro87.MAP_CONSUMER:
        u = v[0] | (v[1] << 8)
        return "media:" + ut.CONSUMER_NAME.get(u, f"0x{u:04x}")
    if m.kind == retro87.MAP_MOUSE:
        return "mouse:" + ut.MOUSE_ACTION_NAME.get(bytes(v[:5]), v[:5].hex())
    if m.kind == 0:
        return "(default)"
    return f"kind={m.kind} value={v.hex()}"


def parse_kb_key(text: str) -> int:
    t = text.strip().lower()
    t = retro87.EXTRA_KEY_ALIASES.get(t, t)
    if t in retro87.EXTRA_KEYS:
        return retro87.EXTRA_KEYS[t]
    code = ut.key_code(t)
    if code is None:
        _die(f"unknown key {text!r}; see 'keyboard keys'")
    return code


def kb_key_name(code: int) -> str:
    return retro87.EXTRA_KEY_NAMES.get(code) or ut.key_name(code)


def parse_kb_macro_steps(steps: List[str]) -> List[retro87.MacroRecord]:
    """Steps: press:KEY release:KEY tap:KEY tap:ctrl+c delay:MS"""
    out: List[retro87.MacroRecord] = []

    def rec(down: bool, code: int) -> retro87.MacroRecord:
        if code in ut.MODIFIER_CODES:
            return retro87.MacroRecord(retro87.REC_MOD_DOWN if down else retro87.REC_MOD_UP, code)
        return retro87.MacroRecord(retro87.REC_KEY_DOWN if down else retro87.REC_KEY_UP, code)

    for step in steps:
        if ":" not in step:
            _die(f"bad macro step {step!r} (use press:KEY, release:KEY, tap:KEY, delay:MS)")
        op, arg = step.lower().split(":", 1)
        if op == "delay":
            out.append(retro87.MacroRecord(retro87.REC_DELAY, int(arg)))
            continue
        codes = []
        for part in arg.split("+"):
            c = ut.key_code(part)
            if c is None:
                _die(f"unknown key {part!r} in step {step!r}")
            codes.append(c)
        if op == "press":
            out.extend(rec(True, c) for c in codes)
        elif op == "release":
            out.extend(rec(False, c) for c in reversed(codes))
        elif op == "tap":
            out.extend(rec(True, c) for c in codes)
            out.extend(rec(False, c) for c in reversed(codes))
        else:
            _die(f"unknown macro step {op!r}")
    return out


def format_kb_macro_steps(records: List[retro87.MacroRecord]) -> List[str]:
    out = []
    for r in records:
        if r.type == retro87.REC_DELAY:
            out.append(f"delay:{r.code}")
        elif r.type in (retro87.REC_KEY_DOWN, retro87.REC_MOD_DOWN):
            out.append(f"press:{ut.key_name(r.code)}")
        elif r.type in (retro87.REC_KEY_UP, retro87.REC_MOD_UP):
            out.append(f"release:{ut.key_name(r.code)}")
        else:
            out.append(f"raw:{r.type:02x}:{r.code:02x}")
    return out


# ----------------------------------------------------------------------------
# mouse: macro steps
# ----------------------------------------------------------------------------
MOUSE_CLICK_CODES = {"left": 0, "right": 1, "middle": 2, "back": 4, "forward": 3}
MOUSE_CLICK_NAMES = {v: k for k, v in MOUSE_CLICK_CODES.items()}


def parse_mouse_macro_steps(steps: List[str]) -> List[r8mouse.MacroRecord]:
    """Steps: press:KEY release:KEY tap:KEY click:left press:mouse_left delay:MS"""
    out: List[r8mouse.MacroRecord] = []

    def keycode(arg: str) -> int:
        mod = 0
        if "+" in arg:
            m, arg = arg.rsplit("+", 1)
            mc = ut.key_code(m)
            if mc is None or mc not in ut.MODIFIER_CODES:
                _die(f"{m!r} is not a modifier")
            mod = mc
        c = ut.key_code(arg)
        if c is None:
            _die(f"unknown key {arg!r}")
        return c | (mod << 8)

    for step in steps:
        if ":" not in step:
            _die(f"bad macro step {step!r}")
        op, arg = step.lower().split(":", 1)
        if op == "delay":
            if not out:
                _die("delay must follow an event")
            out[-1].delay_ms = int(arg)
            continue
        is_mouse = arg.startswith("mouse_") or arg in MOUSE_CLICK_CODES
        if is_mouse:
            btn = arg[6:] if arg.startswith("mouse_") else arg
            if btn not in MOUSE_CLICK_CODES:
                _die(f"unknown mouse button {btn!r} (left/right/middle/back/forward)")
            code = MOUSE_CLICK_CODES[btn]
            down, up = r8mouse.MACRO_MOUSE_PRESS, r8mouse.MACRO_MOUSE_RELEASE
        else:
            code = keycode(arg)
            down, up = r8mouse.MACRO_KEY_PRESS, r8mouse.MACRO_KEY_RELEASE
        if op in ("press",):
            out.append(r8mouse.MacroRecord(down, code, 10))
        elif op == "release":
            out.append(r8mouse.MacroRecord(up, code, 10))
        elif op in ("tap", "click"):
            out.append(r8mouse.MacroRecord(down, code, 10))
            out.append(r8mouse.MacroRecord(up, code, 10))
        else:
            _die(f"unknown macro step {op!r}")
    return out


def format_mouse_macro_steps(records: List[r8mouse.MacroRecord]) -> List[str]:
    out = []
    for r in records:
        if r.state in (r8mouse.MACRO_MOUSE_PRESS, r8mouse.MACRO_MOUSE_RELEASE):
            name = "mouse_" + MOUSE_CLICK_NAMES.get(r.code, str(r.code))
        else:
            mod = r.code >> 8
            name = ut.key_name(r.code & 0xFF)
            if mod:
                name = f"{ut.key_name(mod)}+{name}"
        op = "press" if r.state in (r8mouse.MACRO_KEY_PRESS, r8mouse.MACRO_MOUSE_PRESS) else "release"
        out.append(f"{op}:{name}")
        if r.delay_ms != 10:
            out.append(f"delay:{r.delay_ms}")
    return out


def _repeat(arg: Optional[str], infinite: int) -> int:
    if arg is None:
        return 1
    if arg.lower() in ("hold", "infinite", "loop"):
        return infinite
    return int(arg)


# ----------------------------------------------------------------------------
# list
# ----------------------------------------------------------------------------
def cmd_list(_args) -> None:
    found = False
    for info in hidraw.enumerate_hidraw(vid=hidraw.VENDOR_8BITDO):
        found = True
        role = ""
        if info.pid in retro87.PIDS and info.usage_page == retro87.CONFIG_USAGE_PAGE:
            role = "  <- Retro 87 keyboard config interface"
        elif info.pid == r8mouse.PID and info.usage_page == r8mouse.CONFIG_USAGE_PAGE:
            role = "  <- Retro R8 mouse config interface"
        print(f"{info.node:14s} {info.vid:04x}:{info.pid:04x} iface {info.usb_interface} usage-page 0x{info.usage_page or 0:04x}  {info.name}{role}")
    if not found:
        print("no 8BitDo HID devices found")


# ----------------------------------------------------------------------------
# mouse commands
# ----------------------------------------------------------------------------
def open_mouse(args) -> r8mouse.R8Mouse:
    try:
        return r8mouse.R8Mouse.open(args.device)
    except (r8mouse.R8Error, PermissionError, FileNotFoundError) as e:
        _die(f"cannot open mouse: {e}")


def mouse_show_text(cfg: r8mouse.MouseConfig, version: str, color: Tuple[int, str]) -> None:
    print(f"Retro R8 Mouse  edition={color[1]} (code {color[0]})  firmware={version}")
    print(f"  profile name : {cfg.profile_name!r}")
    print(f"  left-hand    : {'on' if cfg.left_hand else 'off'}")
    print(f"  lift-off     : {cfg.lod} mm")
    print(f"  wheel speed  : {cfg.wheel_speed}   wheel direction: {'reversed' if cfg.wheel_direction else 'normal'}")
    print(f"  DPI X        : {cfg.dpi_x.values}  enabled mask 0b{cfg.dpi_x.enabled_mask:06b}")
    print(f"  DPI Y        : {cfg.dpi_y.values}  enabled mask 0b{cfg.dpi_y.enabled_mask:06b}")
    print(f"  active DPI   : slot {cfg.dpi_index + 1} ({cfg.dpi_x.values[cfg.dpi_index] if cfg.dpi_index < 6 else '?'} dpi)")
    print(f"  polling rate : {cfg.rate.values[cfg.rate.current]} Hz (slot {cfg.rate.current + 1} of {cfg.rate.count}; table {cfg.rate.values})")
    print("  buttons      :")
    for b in cfg.buttons:
        fn = ut.R8_FUNCTION_NAME.get(b.function, str(b.function))
        macro = "  [macro enabled]" if b.macro_enabled else ""
        print(f"     {ut.R8_BUTTON_NAME.get(b.index, b.index):10s} -> {fn}{macro}")
    for m in cfg.macros:
        rep = "hold" if m.cycles == 0xFFFF else m.cycles
        print(f"  macro on {ut.R8_BUTTON_NAME.get(m.button, m.button)}: name={m.name!r} repeat={rep} interval={m.interval_ms}ms")
        print("     " + " ".join(format_mouse_macro_steps(m.records)))


def cmd_mouse(args) -> None:
    sub = args.mouse_cmd
    if sub == "functions":
        for name, v in sorted(ut.R8_FUNCTION.items(), key=lambda kv: kv[1]):
            print(f"{v:4d}  {name}")
        return
    with open_mouse(args) as m:
        if sub == "info":
            v = m.version_raw()
            print(f"firmware (app formula): {m.version()}   raw: {v[:20].hex(' ')}")
            code, name = m.color()
            print(f"edition: {name} (code {code})")
        elif sub == "show":
            cfg = m.read_config()
            if args.json:
                print(json.dumps(_asdict(cfg), indent=2))
            else:
                mouse_show_text(cfg, m.version(), m.color())
        elif sub == "dump":
            print(json.dumps(_asdict(m.read_config()), indent=2))
        elif sub == "apply":
            mouse_apply(m, json.load(open(args.file)))
            print("applied")
        elif sub == "dpi":
            if len(args.values) != 6:
                _die("give exactly 6 DPI values (slots 1..6)")
            mask = 0x3F
            if args.enable:
                mask = 0
                for s in args.enable.split(","):
                    mask |= 1 << (int(s) - 1)
            table = r8mouse.DpiTable(mask, [int(v) for v in args.values])
            for axis in ((0, 1) if args.axis == "both" else ((0,) if args.axis == "x" else (1,))):
                m.set_dpi(axis, table)
            print("DPI X:", m.get_dpi(0)); print("DPI Y:", m.get_dpi(1))
        elif sub == "dpi-slot":
            slot = int(args.slot) - 1
            if not 0 <= slot <= 5:
                _die("slot must be 1..6")
            dpi = m.get_dpi(0).values[slot]
            m.set_dpi_index(slot, dpi)
            print(f"active DPI slot: {m.get_dpi_index() + 1} ({dpi} dpi)")
        elif sub == "rate":
            r = m.get_rate()
            want = int(args.hz)
            if want in r.values:
                r.current = r.values.index(want)
            elif 1 <= want <= r.count:
                r.current = want - 1
            else:
                _die(f"rate must be one of {r.values[:r.count]} Hz or a slot 1..{r.count}")
            m.set_rate(r)
            r = m.get_rate()
            print(f"polling rate: {r.values[r.current]} Hz")
        elif sub == "lod":
            m.set_lod(int(args.mm)); print("lift-off distance:", m.get_lod(), "mm")
        elif sub == "wheel-speed":
            m.set_wheel_speed(int(args.speed)); print("wheel speed:", m.get_wheel_speed())
        elif sub == "wheel-direction":
            m.set_wheel_direction(_onoff(args.value)); print("wheel direction:", "reversed" if m.get_wheel_direction() else "normal")
        elif sub == "left-hand":
            m.set_left_hand(_onoff(args.value)); print("left-hand mode:", "on" if m.get_left_hand() else "off")
        elif sub == "button":
            idx = ut.r8_button_index(args.button)
            if idx is None or idx == 0:
                _die("button must be one of: right, middle, side_front, side_back, right_front, right_back, wheel_up, wheel_down")
            fn = ut.r8_function_value(args.function)
            if fn is None:
                _die(f"unknown function {args.function!r}; see 'mouse functions'")
            cur = {b.index: b for b in m.get_buttons()}[idx]
            m.set_button(idx, fn, cur.macro_enabled if args.keep_macro else 0)
            b = {b.index: b for b in m.get_buttons()}[idx]
            print(f"{ut.R8_BUTTON_NAME[idx]} -> {ut.R8_FUNCTION_NAME.get(b.function, b.function)}")
        elif sub == "macro":
            idx = ut.r8_button_index(args.button)
            if idx is None or idx not in r8mouse.MACRO_SLOT:
                _die("macros can be assigned to side_front, side_back, right_front or right_back")
            recs = parse_mouse_macro_steps(args.steps)
            macro = r8mouse.Macro(button=idx, name=args.name or "macro", cycles=_repeat(args.repeat, 0xFFFF),
                                  interval_ms=args.interval, slot=r8mouse.MACRO_SLOT[idx], records=recs)
            m.assign_macro(macro)
            got = m.get_macro(idx)
            print(f"macro on {ut.R8_BUTTON_NAME[idx]}: {got.name!r}, {len(got.records)} events, repeat {'hold' if got.cycles == 0xFFFF else got.cycles}, interval {got.interval_ms} ms")
        elif sub == "macro-off":
            idx = ut.r8_button_index(args.button)
            if idx is None or idx not in r8mouse.MACRO_SLOT:
                _die("button must be side_front, side_back, right_front or right_back")
            cur = {b.index: b for b in m.get_buttons()}[idx]
            m.set_button(idx, cur.function, 0)
            print(f"macro disabled on {ut.R8_BUTTON_NAME[idx]}")
        elif sub == "profile-name":
            m.set_profile_name(args.name); print("profile name:", repr(m.get_profile_name()))
        elif sub == "reset":
            if not args.yes:
                _die("this restores factory settings; re-run with --yes")
            m.factory_reset(); print("factory reset sent")
        else:
            _die(f"unknown mouse command {sub}")


def mouse_apply(m: r8mouse.R8Mouse, cfg: Dict[str, Any]) -> None:
    if "profile_name" in cfg:
        m.set_profile_name(cfg["profile_name"])
    if "left_hand" in cfg:
        m.set_left_hand(bool(cfg["left_hand"]))
    if "lod" in cfg:
        m.set_lod(int(cfg["lod"]))
    if "wheel_speed" in cfg:
        m.set_wheel_speed(int(cfg["wheel_speed"]))
    if "wheel_direction" in cfg:
        m.set_wheel_direction(bool(cfg["wheel_direction"]))
    for axis, key in ((0, "dpi_x"), (1, "dpi_y")):
        if key in cfg:
            m.set_dpi(axis, r8mouse.DpiTable(int(cfg[key]["enabled_mask"]), [int(v) for v in cfg[key]["values"]]))
    if "dpi_index" in cfg:
        idx = int(cfg["dpi_index"])
        m.set_dpi_index(idx, m.get_dpi(0).values[idx])
    if "rate" in cfg:
        r = cfg["rate"]
        m.set_rate(r8mouse.RateTable(int(r["count"]), int(r["current"]), [int(v) for v in r["values"]]))
    for mac in cfg.get("macros", []):
        recs = [r8mouse.MacroRecord(int(r["state"]), int(r["code"]), int(r["delay_ms"])) for r in mac["records"]]
        if recs:
            m.set_macro(r8mouse.Macro(int(mac["button"]), mac.get("name", ""), int(mac.get("cycles", 1)),
                                      int(mac.get("interval_ms", 0)),
                                      int(mac.get("slot", r8mouse.MACRO_SLOT.get(int(mac["button"]), 1))), recs))
    for b in cfg.get("buttons", []):
        m.set_button(int(b["index"]), int(b["function"]), int(b.get("macro_enabled", 0)))


# ----------------------------------------------------------------------------
# keyboard commands
# ----------------------------------------------------------------------------
def open_keyboard(args) -> retro87.Retro87:
    try:
        return retro87.Retro87.open(args.device)
    except (retro87.Retro87Error, PermissionError, FileNotFoundError) as e:
        _die(f"cannot open keyboard: {e}")


def keyboard_show_text(cfg: retro87.KeyboardConfig) -> None:
    print("Retro 87 Mechanical Keyboard")
    print(f"  profile name : {cfg.profile_name!r}")
    print(f"  volume level : {cfg.volume} (1..5)")
    print(f"  feature flags: {cfg.feature}")
    if cfg.mappings:
        print("  remapped keys:")
        for mp in cfg.mappings:
            print(f"     {kb_key_name(mp.key):14s} -> {format_kb_mapping(mp)}")
    else:
        print("  remapped keys: none")
    if cfg.macros:
        for mc in cfg.macros:
            rep = "hold" if mc.cycles == retro87.MACRO_INFINITE else mc.cycles
            print(f"  macro on {kb_key_name(mc.key)}: name={mc.name!r} repeat={rep} interval={mc.interval_ms}ms")
            print("     " + " ".join(format_kb_macro_steps(mc.records)))
    else:
        print("  macros: none")


def cmd_keyboard(args) -> None:
    sub = args.kb_cmd
    if sub == "keys":
        names = sorted(ut.HID_KEY, key=lambda k: ut.HID_KEY[k])
        print("physical keys / plain targets:", " ".join(names))
        print("extra physical keys:", " ".join(retro87.EXTRA_KEYS))
        return
    if sub == "targets":
        print("keys: any name from 'keyboard keys', optionally with one modifier, e.g. shift+1, ctrl+c, right_alt+f4")
        print("special: fn none")
        print("media:", " ".join("media:" + k for k in ut.CONSUMER))
        print("mouse:", " ".join("mouse:" + k[6:] if k.startswith("mouse_") else "mouse:" + k for k in ut.MOUSE_ACTION))
        return
    with open_keyboard(args) as k:
        if sub == "info":
            info = retro87.find_device() if args.device is None else None
            print("Retro 87 Mechanical Keyboard", f"on {k.dev.node}")
            if info:
                import pathlib
                dev = pathlib.Path("/sys/class/hidraw") / pathlib.Path(info.node).name / "device"
                usb = dev.resolve().parent.parent
                for attr in ("manufacturer", "product", "bcdDevice", "serial"):
                    try:
                        print(f"  {attr}: {(usb / attr).read_text().strip()}")
                    except OSError:
                        pass
            print(f"  volume level: {k.get_volume()}   profile: {k.get_profile_name()!r}")
        elif sub == "show":
            cfg = k.read_config()
            if args.json:
                print(json.dumps(_asdict(cfg), indent=2))
            else:
                keyboard_show_text(cfg)
        elif sub == "dump":
            print(json.dumps(_asdict(k.read_config()), indent=2))
        elif sub == "apply":
            keyboard_apply(k, json.load(open(args.file)))
            print("applied")
        elif sub == "map":
            key = parse_kb_key(args.key)
            kind, value = parse_kb_target(args.target)
            k.set_mapping(key, kind, value)
            print(f"{kb_key_name(key)} -> {format_kb_mapping(k.get_mapping(key))}")
        elif sub == "unmap":
            key = parse_kb_key(args.key)
            k.unmap(key)
            print(f"{kb_key_name(key)} -> {format_kb_mapping(k.get_mapping(key))}")
        elif sub == "macro":
            key = parse_kb_key(args.key)
            recs = parse_kb_macro_steps(args.steps)
            macro = retro87.KeyMacro(key=key, name=args.name or "macro", cycles=_repeat(args.repeat, retro87.MACRO_INFINITE),
                                     interval_ms=args.interval, records=recs)
            k.set_macro(macro)
            got = k.get_macro(key)
            print(f"macro on {kb_key_name(key)}: {got.name!r}, {len(got.records)} events, repeat {'hold' if got.cycles == retro87.MACRO_INFINITE else got.cycles}, interval {got.interval_ms} ms")
        elif sub == "macro-clear":
            key = parse_kb_key(args.key)
            try:
                n = len(k.get_macro(key).records)
            except retro87.Retro87Error:
                n = 0
            k.clear_macro(key, n)
            print(f"macro cleared on {kb_key_name(key)}; macros now on: {[kb_key_name(x) for x in k.get_macro_keys()]}")
        elif sub == "volume":
            k.set_volume(int(args.level)); print("volume level:", k.get_volume())
        elif sub == "profile-name":
            k.set_profile_name(args.name); print("profile name:", repr(k.get_profile_name()))
        elif sub == "reset":
            if not args.yes:
                _die("this clears all remaps, macros and the profile name; re-run with --yes")
            k.reset(); print("reset done; remapped keys:", k.get_mapped_keys(), "macros:", k.get_macro_keys())
        elif sub == "listen":
            print(f"listening for vendor reports for {args.seconds}s (Ctrl-C to stop)")
            try:
                for rep in k.listen(float(args.seconds)):
                    print(rep.hex(" "))
            except KeyboardInterrupt:
                pass
        else:
            _die(f"unknown keyboard command {sub}")


def keyboard_apply(k: retro87.Retro87, cfg: Dict[str, Any]) -> None:
    if "profile_name" in cfg:
        k.set_profile_name(cfg["profile_name"])
    if "volume" in cfg:
        k.set_volume(int(cfg["volume"]))
    if cfg.get("feature"):
        k.set_feature(int(cfg["feature"]))
    for mp in cfg.get("mappings", []):
        if int(mp["kind"]) == 0:
            continue
        k.set_mapping(int(mp["key"]), int(mp["kind"]), bytes(mp["value"]))
    for mc in cfg.get("macros", []):
        recs = [retro87.MacroRecord(int(r["type"]), int(r["code"])) for r in mc["records"]]
        if recs:
            k.set_macro(retro87.KeyMacro(int(mc["key"]), mc.get("name", ""), int(mc.get("cycles", 1)), int(mc.get("interval_ms", 0)), recs))


# ----------------------------------------------------------------------------
# argument parser
# ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="8bitdo-cfg", description="Configure the 8BitDo Retro 87 keyboard and Retro R8 mouse on Linux")
    p.add_argument("--device", help="hidraw node to use instead of auto-detection (e.g. /dev/hidraw6)")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list", help="list 8BitDo HID interfaces").set_defaults(func=cmd_list)
    x = sp.add_parser("ui", help="open the Retro Config web UI in your browser")
    x.add_argument("--port", type=int, default=8765); x.add_argument("--no-browser", action="store_true"); x.add_argument("--verbose", action="store_true")

    m = sp.add_parser("mouse", help="Retro R8 mouse").add_subparsers(dest="mouse_cmd", required=True)
    m.add_parser("info", help="firmware version and edition")
    x = m.add_parser("show", help="show the full configuration"); x.add_argument("--json", action="store_true")
    m.add_parser("dump", help="print configuration as JSON")
    x = m.add_parser("apply", help="apply a JSON configuration"); x.add_argument("file")
    x = m.add_parser("dpi", help="set the 6 DPI slots"); x.add_argument("--axis", choices=["x", "y", "both"], default="both"); x.add_argument("--enable", help="comma separated enabled slots, e.g. 1,2,3"); x.add_argument("values", nargs="+")
    x = m.add_parser("dpi-slot", help="select the active DPI slot (1..6)"); x.add_argument("slot")
    x = m.add_parser("rate", help="set polling rate in Hz (250..8000) or slot"); x.add_argument("hz")
    x = m.add_parser("lod", help="lift-off distance in mm (1 or 2)"); x.add_argument("mm")
    x = m.add_parser("wheel-speed", help="wheel speed 0..14"); x.add_argument("speed")
    x = m.add_parser("wheel-direction", help="normal|reversed"); x.add_argument("value")
    x = m.add_parser("left-hand", help="left-hand mode on|off"); x.add_argument("value")
    x = m.add_parser("button", help="assign a function to a button"); x.add_argument("button"); x.add_argument("function"); x.add_argument("--keep-macro", action="store_true")
    x = m.add_parser("macro", help="assign a macro to a side button"); x.add_argument("button"); x.add_argument("--name"); x.add_argument("--repeat", help="count, or 'loop' (runs until another button is pressed; the mouse has no while-held mode)"); x.add_argument("--interval", type=int, default=0, help="ms between repeats"); x.add_argument("steps", nargs="+", help="press:KEY release:KEY tap:KEY click:left delay:MS")
    x = m.add_parser("macro-off", help="disable the macro on a button"); x.add_argument("button")
    x = m.add_parser("profile-name", help="set the profile name (max 10 chars)"); x.add_argument("name")
    x = m.add_parser("reset", help="factory reset"); x.add_argument("--yes", action="store_true")
    m.add_parser("functions", help="list button function names")

    k = sp.add_parser("keyboard", help="Retro 87 mechanical keyboard").add_subparsers(dest="kb_cmd", required=True)
    k.add_parser("info", help="device information")
    x = k.add_parser("show", help="show the full configuration"); x.add_argument("--json", action="store_true")
    k.add_parser("dump", help="print configuration as JSON")
    x = k.add_parser("apply", help="apply a JSON configuration"); x.add_argument("file")
    x = k.add_parser("map", help="remap a key"); x.add_argument("key"); x.add_argument("target")
    x = k.add_parser("unmap", help="restore a key to its default"); x.add_argument("key")
    x = k.add_parser("macro", help="assign a macro to a key"); x.add_argument("key"); x.add_argument("--name"); x.add_argument("--repeat", help="count or 'hold'"); x.add_argument("--interval", type=int, default=0, help="ms between repeats"); x.add_argument("steps", nargs="+", help="press:KEY release:KEY tap:KEY tap:ctrl+c delay:MS")
    x = k.add_parser("macro-clear", help="remove the macro from a key"); x.add_argument("key")
    x = k.add_parser("volume", help="volume level 1..5"); x.add_argument("level")
    x = k.add_parser("profile-name", help="set the profile name (max 30 chars)"); x.add_argument("name")
    x = k.add_parser("reset", help="clear remaps, macros and profile name"); x.add_argument("--yes", action="store_true")
    x = k.add_parser("listen", help="print raw vendor reports"); x.add_argument("seconds", nargs="?", default="10")
    k.add_parser("keys", help="list key names")
    k.add_parser("targets", help="list remap targets")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "list":
            cmd_list(args)
        elif args.cmd == "ui":
            from .server import serve
            serve(args.port, not args.no_browser, args.verbose)
        elif args.cmd == "mouse":
            cmd_mouse(args)
        elif args.cmd == "keyboard":
            cmd_keyboard(args)
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (r8mouse.R8Error, retro87.Retro87Error, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
