import contextlib
import io
import unittest

from eightbitdo import cli, retro87, r8mouse


class CliParsing(unittest.TestCase):
    def test_keyboard_targets(self):
        self.assertEqual(cli.parse_kb_target("f24"), (7, bytes([0, 0x73, 0, 0])))
        self.assertEqual(cli.parse_kb_target("shift+1"), (7, bytes([0xE1, 0x1E, 0, 0])))
        self.assertEqual(cli.parse_kb_target("right_alt+f4"), (7, bytes([0xE6, 0x3D, 0, 0])))
        self.assertEqual(cli.parse_kb_target("fn"), (7, bytes([0, 3, 0, 0])))
        self.assertEqual(cli.parse_kb_target("media:volume_up"), (12, bytes([0xE9, 0, 0, 0])))
        self.assertEqual(cli.parse_kb_target("mail"), (12, bytes([0x8A, 0x01, 0, 0])))
        self.assertEqual(cli.parse_kb_target("mouse:left"), (1, bytes([1, 0, 0, 0, 0])))
        self.assertEqual(cli.parse_kb_target("mouse:scroll_down"), (1, bytes([0, 0, 0, 0xFE, 0])))
        with self.assertRaises(cli.CliError):
            cli.parse_kb_target("nosuchkey")

    def test_keyboard_target_roundtrip(self):
        for t in ["f24", "shift+1", "fn", "none", "media:mute", "mouse:mouse_right", "mouse:scroll_up"]:
            kind, value = cli.parse_kb_target(t)
            shown = cli.format_kb_mapping(retro87.KeyMapping(4, kind, value))
            kind2, value2 = cli.parse_kb_target(shown)
            self.assertEqual((kind, value), (kind2, value2), t)

    def test_keyboard_macro_steps(self):
        recs = cli.parse_kb_macro_steps(["tap:ctrl+c", "delay:20", "press:a", "release:a"])
        self.assertEqual([(r.type, r.code) for r in recs], [
            (0x83, 0xE0), (0x81, 0x06), (0x01, 0x06), (0x03, 0xE0), (0x0F, 20), (0x81, 4), (0x01, 4)])

    def test_extra_keys(self):
        self.assertEqual(cli.parse_kb_key("key_a"), 109)
        self.assertEqual(cli.parse_kb_key("key_b"), 108)
        self.assertEqual(cli.parse_kb_key("super_a"), 109)  # earlier name
        self.assertEqual(cli.kb_key_name(109), "key_a")
        self.assertEqual(cli.parse_kb_key("k1"), 116)

    def test_udev(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["udev"]), 0)
        self.assertEqual(out.getvalue(), cli.UDEV_RULES.read_text())
        self.assertIn('ATTRS{idProduct}=="5200|5201|5205|5206"', out.getvalue())

    def test_permission_hint(self):
        msg = cli.open_error(PermissionError(13, "Permission denied", "/dev/hidraw6"))
        self.assertIn("Permission denied", msg)
        self.assertIn("8bitdo-cfg udev | sudo tee /etc/udev/rules.d/70-8bitdo.rules", msg)
        self.assertEqual(cli.open_error(FileNotFoundError("gone")), "gone")

    def test_mouse_macro_steps(self):
        recs = cli.parse_mouse_macro_steps(["click:left", "delay:50", "tap:shift+1"])
        self.assertEqual([(r.state, r.code, r.delay_ms) for r in recs], [
            (15, 0, 10), (7, 0, 50), (10, 0x1E | (0xE1 << 8), 10), (2, 0x1E | (0xE1 << 8), 10)])
        shown = cli.format_mouse_macro_steps(recs)
        self.assertEqual(shown, ["press:mouse_left", "release:mouse_left", "delay:50", "press:left_shift+1", "release:left_shift+1"])

    def test_parser(self):
        p = cli.build_parser()
        a = p.parse_args(["mouse", "dpi", "--axis", "x", "--enable", "1,2", "800", "1600", "3200", "6400", "12800", "26000"])
        self.assertEqual(a.mouse_cmd, "dpi")
        self.assertEqual(len(a.values), 6)
        a = p.parse_args(["keyboard", "map", "caps_lock", "left_ctrl"])
        self.assertEqual((a.kb_cmd, a.key, a.target), ("map", "caps_lock", "left_ctrl"))


if __name__ == "__main__":
    unittest.main()
