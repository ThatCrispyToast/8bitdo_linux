"""Local web UI (``8bitdo-cfg ui``): a stdlib HTTP server with a small JSON API
over the device modules, serving the single-file front end in ``ui/``.

Binds to 127.0.0.1 only.  POSTs must carry ``X-Requested-With: retro-config``
so a random web page cannot drive the devices through the browser.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from . import cli, r8mouse, retro87, usage_tables as ut

UI_DIR = Path(__file__).parent / "ui"
DEFAULT_PORT = 8765
REQUIRED_HEADER = ("X-Requested-With", "retro-config")

FONT_FACES = [
    ("press-start-2p-400", "Press Start 2P", 400),
    ("ibm-plex-sans-400", "IBM Plex Sans", 400),
    ("ibm-plex-sans-500", "IBM Plex Sans", 500),
    ("ibm-plex-sans-600", "IBM Plex Sans", 600),
    ("ibm-plex-mono-400", "IBM Plex Mono", 400),
    ("ibm-plex-mono-500", "IBM Plex Mono", 500),
]


# ----------------------------------------------------------------------------
# metadata and state serialisation
# ----------------------------------------------------------------------------
def pretty(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


R8_LABELS = {
    "dpi_up": "DPI +", "dpi_down": "DPI -", "dpi_cycle": "DPI cycle", "rgb_toggle": "RGB on/off",
    "polling_rate_cycle": "Polling rate cycle", "led_mode_cycle": "LED mode cycle",
    "2p4g_mode": "2.4 GHz mode", "ble_mode": "Bluetooth mode", "left_gui": "Left Win/Cmd",
    "right_gui": "Right Win/Cmd", "kp_slash": "Keypad /", "kp_asterisk": "Keypad *",
    "kp_minus": "Keypad -", "kp_plus": "Keypad +", "kp_period": "Keypad .", "kp_enter": "Keypad Enter",
    "esc": "Esc", "page_up": "Page Up", "page_down": "Page Down", "print_screen": "Print Screen",
    "mac_page_up": "Page Up (Mac)", "mac_page_down": "Page Down (Mac)", "ml": "ML", "mr": "MR",
    "r4": "R4", "r5": "R5", "fetch_chatgpt": "Open ChatGPT", "custom_ai": "Custom AI", "disabled": "Disabled (does nothing)",
}


def r8_label(name: str) -> str:
    if name in R8_LABELS:
        return R8_LABELS[name]
    if re.fullmatch(r"f\d+", name):
        return name.upper()
    if len(name) == 1:
        return name.upper()
    if name.startswith("kp_"):
        return "Keypad " + name[3:]
    if name.startswith("shift_"):
        return "Shift + " + name[6:].replace("_", " ")
    if name.startswith("win_"):
        return pretty(name[4:]) + " (Windows)"
    if name.startswith("mac_"):
        return pretty(name[4:]) + " (Mac)"
    return pretty(name)


def meta() -> Dict[str, Any]:
    keys = [{"name": n, "code": c} for n, c in sorted(ut.HID_KEY.items(), key=lambda kv: kv[1]) if c]
    functions = [
        {"value": v, "name": n, "label": r8_label(n), "group": ut.r8_function_group(v)}
        for n, v in sorted(ut.R8_FUNCTION.items(), key=lambda kv: kv[1])
    ]
    return {
        "keys": keys,
        "extra_keys": retro87.EXTRA_KEYS,
        "consumer": [{"name": n, "code": c, "label": pretty(n)} for n, c in ut.CONSUMER.items()],
        "mouse_actions": list(ut.MOUSE_ACTION),
        "r8_functions": functions,
        "r8_buttons": ut.R8_BUTTON,
        "r8_macro_buttons": sorted(r8mouse.MACRO_SLOT),
        "dpi_range": [r8mouse.DPI_MIN, r8mouse.DPI_MAX],
        "wheel_speed_max": r8mouse.WHEEL_SPEED_MAX,
        "kb_macro_max": retro87.MACRO_MAX_RECORDS,
        "mouse_macro_max": r8mouse.MACRO_MAX_RECORDS,
    }


def usb_info(node: str) -> Dict[str, str]:
    """USB descriptor strings for a hidraw node (product, bcdDevice, serial)."""
    out: Dict[str, str] = {}
    try:
        dev = (Path("/sys/class/hidraw") / Path(node).name / "device").resolve()
        usb = dev.parent.parent
        for attr in ("manufacturer", "product", "bcdDevice", "serial"):
            p = usb / attr
            if p.exists():
                out[attr] = p.read_text().strip()
    except OSError:
        pass
    return out


def keyboard_state(k: retro87.Retro87) -> Dict[str, Any]:
    cfg = k.read_config()
    info = usb_info(k.dev.node)
    return {
        "connected": True,
        "node": k.dev.node,
        "product": info.get("product", "8BitDo Retro Keyboard"),
        "revision": info.get("bcdDevice", ""),
        "profile_name": cfg.profile_name,
        "volume": cfg.volume,
        "feature": cfg.feature,
        "mappings": {
            str(m.key): {"key": m.key, "key_name": cli.kb_key_name(m.key), "kind": m.kind,
                          "value": list(m.value), "target": cli.format_kb_mapping(m)}
            for m in cfg.mappings
        },
        "macros": {
            str(m.key): {"key": m.key, "key_name": cli.kb_key_name(m.key), "name": m.name,
                          "cycles": m.cycles, "interval_ms": m.interval_ms,
                          "steps": cli.format_kb_macro_steps(m.records)}
            for m in cfg.macros
        },
    }


def mouse_state(m: r8mouse.R8Mouse) -> Dict[str, Any]:
    cfg = m.read_config()
    code, edition = m.color()
    return {
        "connected": True,
        "node": m.dev.node,
        "edition": edition,
        "edition_code": code,
        "version": m.version(),
        "profile_name": cfg.profile_name,
        "left_hand": cfg.left_hand,
        "lod": cfg.lod,
        "wheel_speed": cfg.wheel_speed,
        "wheel_direction": cfg.wheel_direction,
        "dpi_x": {"enabled_mask": cfg.dpi_x.enabled_mask, "values": cfg.dpi_x.values},
        "dpi_y": {"enabled_mask": cfg.dpi_y.enabled_mask, "values": cfg.dpi_y.values},
        "dpi_index": cfg.dpi_index,
        "rate": {"count": cfg.rate.count, "current": cfg.rate.current, "values": cfg.rate.values},
        "buttons": [
            {"index": b.index, "name": ut.R8_BUTTON_NAME.get(b.index, str(b.index)), "function": b.function,
             "function_name": ut.R8_FUNCTION_NAME.get(b.function, str(b.function)),
             "macro_enabled": b.macro_enabled}
            for b in cfg.buttons
        ],
        "macros": [
            {"button": mc.button, "button_name": ut.R8_BUTTON_NAME.get(mc.button, str(mc.button)), "name": mc.name,
             "cycles": mc.cycles, "interval_ms": mc.interval_ms, "slot": mc.slot,
             "steps": cli.format_mouse_macro_steps(mc.records)}
            for mc in cfg.macros
        ],
    }


# ----------------------------------------------------------------------------
# actions
# ----------------------------------------------------------------------------
def _key(body: Dict[str, Any]) -> int:
    key = body.get("key")
    if isinstance(key, int):
        return key
    return cli.parse_kb_key(str(key))


def keyboard_action(k: retro87.Retro87, action: str, body: Dict[str, Any]) -> None:
    if action == "map":
        kind, value = cli.parse_kb_target(str(body["target"]))
        k.set_mapping(_key(body), kind, value)
    elif action == "unmap":
        k.unmap(_key(body))
    elif action == "macro":
        recs = cli.parse_kb_macro_steps([str(s) for s in body.get("steps", [])])
        if not recs:
            raise cli.CliError("a macro needs at least one step")
        k.set_macro(retro87.KeyMacro(key=_key(body), name=str(body.get("name") or "macro"),
                                     cycles=cli._repeat(str(body.get("repeat", 1)), retro87.MACRO_INFINITE),
                                     interval_ms=int(body.get("interval_ms", 0)), records=recs))
    elif action == "macro_clear":
        key = _key(body)
        try:
            n = len(k.get_macro(key).records)
        except retro87.Retro87Error:
            n = 0
        k.clear_macro(key, n)
    elif action == "volume":
        k.set_volume(int(body["level"]))
    elif action == "name":
        k.set_profile_name(str(body.get("name", "")))
    elif action == "reset":
        k.reset()
    elif action == "apply":
        cli.keyboard_apply(k, body["config"])
    else:
        raise cli.CliError(f"unknown keyboard action {action!r}")


def _button(body: Dict[str, Any]) -> int:
    b = body.get("button")
    idx = b if isinstance(b, int) else ut.r8_button_index(str(b))
    if idx is None or idx == 0 or idx not in ut.R8_BUTTON_NAME:
        raise cli.CliError("button must be right, middle, side_front, side_back, right_front, right_back, wheel_up or wheel_down")
    return idx


def mouse_action(m: r8mouse.R8Mouse, action: str, body: Dict[str, Any]) -> None:
    if action == "dpi":
        values = [int(v) for v in body["values"]]
        table = r8mouse.DpiTable(int(body.get("enabled_mask", 0x3F)), values)
        axis = body.get("axis", "both")
        for a in ((0, 1) if axis == "both" else ((0,) if axis == "x" else (1,))):
            m.set_dpi(a, table)
    elif action == "dpi_slot":
        slot = int(body["slot"])
        if not 0 <= slot <= 5:
            raise cli.CliError("slot must be 0..5")
        m.set_dpi_index(slot, m.get_dpi(0).values[slot])
    elif action == "rate":
        r = m.get_rate()
        hz = int(body["hz"])
        if hz not in r.values[:r.count]:
            raise cli.CliError(f"rate must be one of {r.values[:r.count]}")
        r.current = r.values.index(hz)
        m.set_rate(r)
    elif action == "lod":
        m.set_lod(int(body["mm"]))
    elif action == "wheel_speed":
        m.set_wheel_speed(int(body["value"]))
    elif action == "wheel_direction":
        m.set_wheel_direction(bool(body["reversed"]))
    elif action == "left_hand":
        m.set_left_hand(bool(body["on"]))
    elif action == "button":
        idx = _button(body)
        fn = body.get("function")
        value = fn if isinstance(fn, int) else ut.r8_function_value(str(fn))
        if value is None:
            raise cli.CliError(f"unknown function {fn!r}")
        cur = {b.index: b for b in m.get_buttons()}[idx]
        m.set_button(idx, value, cur.macro_enabled if body.get("keep_macro") else 0)
    elif action == "macro":
        idx = _button(body)
        if idx not in r8mouse.MACRO_SLOT:
            raise cli.CliError("macros can only go on the side buttons")
        recs = cli.parse_mouse_macro_steps([str(s) for s in body.get("steps", [])])
        if not recs:
            raise cli.CliError("a macro needs at least one step")
        m.assign_macro(r8mouse.Macro(button=idx, name=str(body.get("name") or "macro"),
                                     cycles=cli._repeat(str(body.get("repeat", 1)), 0xFFFF),
                                     interval_ms=int(body.get("interval_ms", 0)), slot=r8mouse.MACRO_SLOT[idx], records=recs))
    elif action == "macro_off":
        idx = _button(body)
        cur = {b.index: b for b in m.get_buttons()}[idx]
        m.set_button(idx, cur.function, 0)
    elif action == "name":
        m.set_profile_name(str(body.get("name", "")))
    elif action == "reset":
        m.factory_reset()
    elif action == "apply":
        cli.mouse_apply(m, body["config"])
    else:
        raise cli.CliError(f"unknown mouse action {action!r}")


class Api:
    """Device access for the HTTP layer; factories are injectable for tests."""

    def __init__(self, kb_factory: Optional[Callable] = None, mouse_factory: Optional[Callable] = None):
        self.kb_factory = kb_factory or retro87.Retro87.open
        self.mouse_factory = mouse_factory or r8mouse.R8Mouse.open
        self.lock = threading.Lock()

    def state(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"keyboard": None, "mouse": None, "errors": {}}
        with self.lock:
            try:
                with self.kb_factory() as k:
                    out["keyboard"] = keyboard_state(k)
            except Exception as e:  # noqa: BLE001 - reported to the UI
                out["errors"]["keyboard"] = cli.open_error(e)
            try:
                with self.mouse_factory() as m:
                    out["mouse"] = mouse_state(m)
            except Exception as e:  # noqa: BLE001
                out["errors"]["mouse"] = cli.open_error(e)
        return out

    def dump(self, device: str) -> Dict[str, Any]:
        with self.lock:
            if device == "keyboard":
                with self.kb_factory() as k:
                    return cli._asdict(k.read_config())
            with self.mouse_factory() as m:
                return cli._asdict(m.read_config())

    def post(self, device: str, action: str, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if device == "keyboard":
                with self.kb_factory() as k:
                    keyboard_action(k, action, body)
                    return {"ok": True, "keyboard": keyboard_state(k)}
            if device == "mouse":
                with self.mouse_factory() as m:
                    mouse_action(m, action, body)
                    return {"ok": True, "mouse": mouse_state(m)}
            raise cli.CliError(f"unknown device {device!r}")


# ----------------------------------------------------------------------------
# page assembly
# ----------------------------------------------------------------------------
def font_css() -> str:
    parts = []
    for fname, family, weight in FONT_FACES:
        p = UI_DIR / "fonts" / f"{fname}.woff2"
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        parts.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
        )
    return "\n".join(parts)


def demo_state() -> Dict[str, Any]:
    """Sample data for the page when no local server is reachable (demo / preview)."""
    def kb_map(key: int, target: str) -> Dict[str, Any]:
        return {"key": key, "key_name": cli.kb_key_name(key), "kind": 7, "value": [0, 0, 0, 0], "target": target}
    dpi = {"enabled_mask": 63, "values": [800, 1200, 1600, 2400, 3200, 6400]}
    return {
        "demo": True,
        "keyboard": {
            "connected": True, "node": "/dev/hidraw6", "product": "8BitDo Retro Keyboard", "revision": "0177",
            "profile_name": "Sample profile", "volume": 3, "feature": 0,
            "mappings": {
                "57": kb_map(57, "left_ctrl"), "71": kb_map(71, "media:play_pause"),
                "116": kb_map(116, "mouse:left"), "117": kb_map(117, "mouse:right"),
            },
            "macros": {"115": {"key": 115, "key_name": "f24", "name": "Paste as plain", "cycles": 1, "interval_ms": 0,
                                "steps": ["press:left_ctrl", "press:left_shift", "press:v", "release:v", "release:left_shift", "release:left_ctrl"]}},
        },
        "mouse": {
            "connected": True, "node": "/dev/hidraw2", "edition": "n-edition", "edition_code": 1, "version": "10.14",
            "profile_name": "Sample profile", "left_hand": 0, "lod": 1, "wheel_speed": 4, "wheel_direction": 0,
            "dpi_x": dpi, "dpi_y": dict(dpi), "dpi_index": 2,
            "rate": {"count": 6, "current": 2, "values": [250, 500, 1000, 2000, 4000, 8000]},
            "buttons": [
                {"index": 1, "name": "right", "function": 2, "function_name": "right_click", "macro_enabled": 0},
                {"index": 2, "name": "middle", "function": 3, "function_name": "middle_click", "macro_enabled": 0},
                {"index": 3, "name": "side_front", "function": 26, "function_name": "dpi_cycle", "macro_enabled": 0},
                {"index": 4, "name": "side_back", "function": 4, "function_name": "back", "macro_enabled": 1},
                {"index": 5, "name": "right_front", "function": 65, "function_name": "copy", "macro_enabled": 0},
                {"index": 6, "name": "right_back", "function": 255, "function_name": "disabled", "macro_enabled": 0},
                {"index": 7, "name": "wheel_down", "function": 32, "function_name": "scroll_down", "macro_enabled": 0},
                {"index": 8, "name": "wheel_up", "function": 33, "function_name": "scroll_up", "macro_enabled": 0},
            ],
            "macros": [{"button": 4, "button_name": "side_back", "name": "Double click", "cycles": 1, "interval_ms": 0, "slot": 2,
                        "steps": ["press:mouse_left", "release:mouse_left", "delay:80", "press:mouse_left", "release:mouse_left"]}],
        },
        "errors": {},
    }


def build_page(demo: bool = False, wrap: bool = True) -> str:
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__FONTS__*/", font_css())
    inject = "window.META = " + json.dumps(meta()) + ";"
    if demo:
        inject += "\nwindow.DEMO_STATE = " + json.dumps(demo_state()) + ";"
    html = html.replace("/*__META__*/", inject)
    if wrap:
        html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>\n'
                + html + "\n</body></html>\n")
    return html


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    api: Api
    page: bytes
    verbose = False

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            return False
        return self.headers.get(REQUIRED_HEADER[0]) == REQUIRED_HEADER[1]

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, self.page, "text/html; charset=utf-8")
        elif path == "/api/state":
            self._json(HTTPStatus.OK, self.api.state())
        elif path == "/api/meta":
            self._json(HTTPStatus.OK, meta())
        elif path in ("/api/keyboard/dump", "/api/mouse/dump"):
            try:
                self._json(HTTPStatus.OK, self.api.dump(path.split("/")[2]))
            except Exception as e:  # noqa: BLE001
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": str(e)})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/(keyboard|mouse)/([a-z_]+)", path)
        if not m:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        if not self._same_origin():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "forbidden"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            result = self.api.post(m.group(1), m.group(2), body)
            self._json(HTTPStatus.OK, result)
        except (cli.CliError, ValueError, KeyError, TypeError) as e:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(e)})

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.verbose:
            super().log_message(fmt, *args)


def serve(port: int = DEFAULT_PORT, open_browser: bool = True, verbose: bool = False) -> None:
    page = build_page().encode("utf-8")
    handler = type("RetroConfigHandler", (Handler,), {"api": Api(), "page": page, "verbose": verbose})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Retro Config UI at {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Retro Config web UI")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--export", metavar="FILE", help="write a standalone demo page instead of serving")
    a = p.parse_args(argv)
    if a.export:
        Path(a.export).write_text(build_page(demo=True, wrap=False), encoding="utf-8")
        print(f"wrote {a.export}")
        return 0
    serve(a.port, not a.no_browser, a.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
