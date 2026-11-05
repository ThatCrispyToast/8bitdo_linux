import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from eightbitdo import server, retro87, r8mouse, usage_tables as ut


class FakeKeyboard:
    """Just enough of Retro87 for the API layer."""

    def __init__(self):
        self.dev = type("D", (), {"node": "/dev/hidraw99"})()
        self.mappings = {}
        self.macros = {}
        self.volume = 2
        self.name = ""
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def read_config(self):
        return retro87.KeyboardConfig(self.name, self.volume, 0, list(self.mappings.values()), list(self.macros.values()))

    def set_mapping(self, key, kind, value):
        self.calls.append(("set_mapping", key, kind, bytes(value)))
        self.mappings[key] = retro87.KeyMapping(key, kind, bytes(value))

    def unmap(self, key):
        self.calls.append(("unmap", key))
        self.mappings.pop(key, None)

    def set_macro(self, macro):
        self.calls.append(("set_macro", macro.key, len(macro.records)))
        self.macros[macro.key] = macro

    def get_macro(self, key):
        return self.macros[key]

    def clear_macro(self, key, n):
        self.calls.append(("clear_macro", key, n))
        self.macros.pop(key, None)

    def set_volume(self, level):
        self.volume = level

    def set_profile_name(self, name):
        self.name = name

    def reset(self):
        self.mappings.clear(); self.macros.clear(); self.name = ""


class FakeMouse:
    def __init__(self):
        self.dev = type("D", (), {"node": "/dev/hidraw98"})()
        self.buttons = [r8mouse.ButtonMapping(i, f, 0) for i, f in ((1, 2), (2, 3), (3, 5), (4, 4), (5, 255), (6, 255), (7, 32), (8, 33))]
        self.dpi = {0: r8mouse.DpiTable(63, [800, 1200, 1600, 2400, 3200, 6400]), 1: r8mouse.DpiTable(63, [800, 1200, 1600, 2400, 3200, 6400])}
        self.rate = r8mouse.RateTable(6, 1, [250, 500, 1000, 2000, 4000, 8000])
        self.dpi_index = 1
        self.lod = 1; self.wheel_speed = 0; self.wheel_dir = 0; self.left = 0; self.name = ""
        self.macros = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def color(self):
        return 1, "n-edition"

    def version(self):
        return "10.14"

    def read_config(self):
        return r8mouse.MouseConfig(self.name, self.left, self.lod, self.wheel_speed, self.wheel_dir, list(self.buttons),
                                   self.dpi[0], self.dpi[1], self.dpi_index, self.rate, list(self.macros.values()))

    def get_buttons(self):
        return list(self.buttons)

    def set_button(self, index, function, macro_enabled=0):
        pos = [b.index for b in self.buttons].index(index)
        self.buttons[pos] = r8mouse.ButtonMapping(index, function, macro_enabled)

    def get_dpi(self, axis):
        return self.dpi[axis]

    def set_dpi(self, axis, table):
        self.dpi[axis] = table

    def set_dpi_index(self, index, dpi):
        self.dpi_index = index

    def get_rate(self):
        return self.rate

    def set_rate(self, table):
        self.rate = table

    def set_lod(self, mm):
        self.lod = mm

    def set_wheel_speed(self, v):
        self.wheel_speed = v

    def set_wheel_direction(self, r):
        self.wheel_dir = 1 if r else 0

    def set_left_hand(self, on):
        self.left = 1 if on else 0

    def set_profile_name(self, n):
        self.name = n

    def set_macro(self, macro):
        self.macros[macro.button] = macro

    def assign_macro(self, macro, function=None):
        cur = {b.index: b for b in self.buttons}[macro.button]
        self.set_button(macro.button, cur.function if function is None else function, 1)
        self.set_macro(macro)

    def get_macro(self, button):
        return self.macros[button]

    def factory_reset(self):
        self.__init__()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.kb = FakeKeyboard(); self.ms = FakeMouse()
        self.api = server.Api(kb_factory=lambda: self.kb, mouse_factory=lambda: self.ms)

    def test_state_shape(self):
        s = self.api.state()
        self.assertTrue(s["keyboard"]["connected"]); self.assertEqual(s["keyboard"]["volume"], 2)
        self.assertEqual(s["mouse"]["edition"], "n-edition"); self.assertEqual(len(s["mouse"]["buttons"]), 8)
        self.assertEqual(s["mouse"]["buttons"][4]["function_name"], "disabled")
        self.assertEqual(s["mouse"]["buttons"][2]["function_name"], "forward")
        json.dumps(s)  # serialisable

    def test_state_reports_missing_device(self):
        def boom():
            raise retro87.Retro87Error("not found")
        api = server.Api(kb_factory=boom, mouse_factory=lambda: self.ms)
        s = api.state()
        self.assertIsNone(s["keyboard"]); self.assertEqual(s["errors"]["keyboard"], "not found")

    def test_keyboard_map_by_name_and_code(self):
        r = self.api.post("keyboard", "map", {"key": "caps_lock", "target": "left_ctrl"})
        self.assertTrue(r["ok"]); self.assertEqual(r["keyboard"]["mappings"]["57"]["target"], "left_ctrl")
        self.assertEqual(self.kb.calls[-1], ("set_mapping", 57, 7, bytes([0, 0xE0, 0, 0])))
        r = self.api.post("keyboard", "map", {"key": 71, "target": "media:play_pause"})
        self.assertEqual(r["keyboard"]["mappings"]["71"]["target"], "media:play_pause")
        r = self.api.post("keyboard", "unmap", {"key": "caps_lock"})
        self.assertNotIn("57", r["keyboard"]["mappings"])

    def test_keyboard_macro_roundtrip(self):
        r = self.api.post("keyboard", "macro", {"key": "f24", "name": "copy", "repeat": "hold", "interval_ms": 100, "steps": ["tap:ctrl+c", "delay:20"]})
        m = r["keyboard"]["macros"]["115"]
        self.assertEqual(m["cycles"], 255); self.assertEqual(m["interval_ms"], 100)
        self.assertEqual(m["steps"], ["press:left_ctrl", "press:c", "release:c", "release:left_ctrl", "delay:20"])
        r = self.api.post("keyboard", "macro_clear", {"key": "f24"})
        self.assertEqual(r["keyboard"]["macros"], {})

    def test_keyboard_bad_target_is_client_error(self):
        from eightbitdo.cli import CliError
        with self.assertRaises(CliError):
            self.api.post("keyboard", "map", {"key": "a", "target": "nosuchkey"})

    def test_mouse_actions(self):
        r = self.api.post("mouse", "dpi", {"axis": "both", "values": [400, 800, 1600, 3200, 6400, 12800], "enabled_mask": 7})
        self.assertEqual(r["mouse"]["dpi_x"]["values"][0], 400); self.assertEqual(r["mouse"]["dpi_y"]["enabled_mask"], 7)
        r = self.api.post("mouse", "rate", {"hz": 4000}); self.assertEqual(r["mouse"]["rate"]["current"], 4)
        r = self.api.post("mouse", "button", {"button": "side_front", "function": "dpi_cycle"})
        self.assertEqual(r["mouse"]["buttons"][2]["function_name"], "dpi_cycle")
        r = self.api.post("mouse", "macro", {"button": "side_back", "name": "dbl", "repeat": 1, "interval_ms": 0, "steps": ["click:left", "delay:80", "click:left"]})
        self.assertEqual(r["mouse"]["buttons"][3]["macro_enabled"], 1)
        self.assertEqual(r["mouse"]["macros"][0]["steps"], ["press:mouse_left", "release:mouse_left", "delay:80", "press:mouse_left", "release:mouse_left"])
        r = self.api.post("mouse", "macro_off", {"button": 4}); self.assertEqual(r["mouse"]["buttons"][3]["macro_enabled"], 0)
        # right-side pair: positions 5/6, macro slots 3/4, "r4"/"r5" accepted as aliases
        r = self.api.post("mouse", "button", {"button": "right_back", "function": "copy"})
        self.assertEqual((r["mouse"]["buttons"][5]["index"], r["mouse"]["buttons"][5]["function_name"]), (6, "copy"))
        r = self.api.post("mouse", "macro", {"button": "r4", "name": "m3", "steps": ["click:left"]})
        self.assertEqual((r["mouse"]["buttons"][4]["index"], r["mouse"]["buttons"][4]["macro_enabled"]), (5, 1))
        self.assertEqual([(m["button"], m["slot"]) for m in r["mouse"]["macros"]], [(4, 2), (5, 3)])  # (4, 2) is stored but off
        r = self.api.post("mouse", "button", {"button": "wheel_up", "function": "disabled"})
        self.assertEqual((r["mouse"]["buttons"][7]["index"], r["mouse"]["buttons"][7]["function"]), (8, 255))
        r = self.api.post("mouse", "button", {"button": 8, "function": "scroll_down"})
        self.assertEqual(r["mouse"]["buttons"][7]["function_name"], "scroll_down")
        self.assertEqual(ut.r8_button_index("7"), 7); self.assertIsNone(ut.r8_button_index("9"))
        r = self.api.post("mouse", "wheel_direction", {"reversed": True}); self.assertEqual(r["mouse"]["wheel_direction"], 1)
        r = self.api.post("mouse", "dpi_slot", {"slot": 3}); self.assertEqual(r["mouse"]["dpi_index"], 3)
        from eightbitdo.cli import CliError
        with self.assertRaises(CliError):
            self.api.post("mouse", "macro", {"button": "right", "name": "x", "steps": ["click:left"]})
        for bad in (0, 9, "left"):
            with self.assertRaises(CliError):
                self.api.post("mouse", "button", {"button": bad, "function": "copy"})
        with self.assertRaises(CliError):  # the wheel directions cannot carry macros
            self.api.post("mouse", "macro", {"button": "wheel_down", "name": "x", "steps": ["click:left"]})

    def test_page_builds(self):
        html = server.build_page(demo=True, wrap=False)
        self.assertNotIn("__META__", html); self.assertNotIn("__FONTS__", html)
        self.assertIn("window.DEMO_STATE", html); self.assertIn("<title>Retro Config</title>", html)
        self.assertIn("@font-face", html)
        wrapped = server.build_page(demo=False)
        self.assertTrue(wrapped.startswith("<!doctype html>")); self.assertNotIn("window.DEMO_STATE =", wrapped)

    def test_meta(self):
        m = server.meta()
        self.assertEqual(m["r8_functions"][1]["label"], "Left click")
        self.assertEqual(m["r8_functions"][26]["label"], "DPI cycle")
        self.assertTrue(all(f["group"] for f in m["r8_functions"]))



class StubApi:
    """Records what reached the device layer."""

    def __init__(self):
        self.calls = []

    def post(self, device, action, body):
        self.calls.append((device, action))
        return {"ok": True}

    def state(self):
        return {"keyboard": None, "mouse": None, "errors": {}}


class HttpSecurity(unittest.TestCase):
    def setUp(self):
        self.api = StubApi()
        handler = type("H", (server.Handler,), {"api": self.api, "page": b"<p>ui</p>", "verbose": False})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method, path, host, origin=None, header=True):
        headers = {"Host": host, "Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        if header:
            headers[server.REQUIRED_HEADER[0]] = server.REQUIRED_HEADER[1]
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request(method, path, body="{}" if method == "POST" else None, headers=headers)
        status = c.getresponse().status
        c.close()
        return status

    def test_local_page_works(self):
        for host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            self.assertEqual(self.request("GET", "/", host), 200)
            self.assertEqual(self.request("GET", "/api/state", host), 200)
            self.assertEqual(self.request("POST", "/api/keyboard/reset", host, f"http://{host}"), 200)
        self.assertEqual(len(self.api.calls), 2)

    def test_dns_rebinding_is_refused(self):
        evil = f"evil.example:{self.port}"
        self.assertEqual(self.request("GET", "/", evil), 403)
        self.assertEqual(self.request("GET", "/api/state", evil), 403)
        self.assertEqual(self.request("POST", "/api/keyboard/reset", evil, f"http://{evil}"), 403)
        self.assertEqual(self.request("POST", "/api/keyboard/reset", f"127.0.0.1:{self.port + 1}"), 403)
        self.assertEqual(self.api.calls, [])

    def test_cross_site_post_is_refused(self):
        local = f"127.0.0.1:{self.port}"
        self.assertEqual(self.request("POST", "/api/keyboard/reset", local, "http://evil.example"), 403)
        self.assertEqual(self.request("POST", "/api/keyboard/reset", local, f"http://{local}", header=False), 403)
        self.assertEqual(self.api.calls, [])


if __name__ == "__main__":
    unittest.main()
