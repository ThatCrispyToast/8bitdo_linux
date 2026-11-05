import unittest

from eightbitdo import retro87
from eightbitdo.retro87 import Retro87, KeyMacro, MacroRecord, REC_KEY_DOWN, REC_KEY_UP, REC_DELAY, MACRO_INFINITE
from tests.fake_hid import FakeHidraw


def ack_responder(buf):
    return [bytes([retro87.REPORT_IN, 0xE4, 0x08]) + bytes(30)]


class KeyboardFraming(unittest.TestCase):
    def setUp(self):
        self.dev = FakeHidraw(ack_responder)
        self.k = Retro87(self.dev)

    def test_report_ids_and_length(self):
        self.k.set_volume(3)
        w = self.dev.writes[-1]
        self.assertEqual(len(w), 33)
        self.assertEqual(w[0], retro87.REPORT_OUT)
        self.assertEqual(w[1:3], bytes([retro87.CMD_SET_VOLUME, 3]))

    def test_volume_range(self):
        with self.assertRaises(ValueError):
            self.k.set_volume(0)

    def test_mapping_packet(self):
        self.k.map_key(0x47, 0x73, modifier=0xE1)
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[:13], bytes([0xFA, 3, 0x0C, 0, 0xAA, 9, 0x71, 0x47, 7, 0xE1, 0x73, 0, 0]))
        self.k.map_consumer(0x04, 0x00EA)
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[7:13], bytes([0x04, 12, 0xEA, 0, 0, 0]))
        self.k.map_mouse(0x05, bytes([0, 0, 0, 2, 0]))
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[7:14], bytes([0x05, 1, 0, 0, 0, 2, 0]))

    def test_name_chunks(self):
        self.k.set_profile_name("a" * 40)  # 80 bytes utf-16 -> capped at 60 -> 3 chunks
        ws = [w[1:] for w in self.dev.writes]
        self.assertEqual(len(ws), 3)
        self.assertEqual(ws[0][:3], bytes([retro87.CMD_SET_NAME, 29, 1]))
        self.assertEqual(ws[1][:3], bytes([retro87.CMD_SET_NAME, 29, 1]))
        self.assertEqual(ws[2][:3], bytes([retro87.CMD_SET_NAME, 2, 0]))

    def test_reset_packet(self):
        self.k.reset()
        self.assertEqual(self.dev.writes[-1][1:4], bytes([retro87.CMD_SET_NAME, 0, 0]))

    def test_short_macro_single_packet(self):
        recs = [MacroRecord(REC_KEY_DOWN, 4), MacroRecord(REC_KEY_UP, 4)]
        self.k.set_macro(KeyMacro(key=0x47, name="t", cycles=1, records=recs))
        ws = [w[1:] for w in self.dev.writes]
        self.assertEqual(ws[0][:2], bytes([retro87.CMD_SET_MACRO_NAME, 0x47]))
        pkt = ws[-1]
        self.assertEqual(pkt[:6], bytes([retro87.CMD_SET_MACRO, 0x47, 0, 0, 0, 26]))
        self.assertEqual(pkt[6:10], bytes([1, 1, 0, 2]))
        self.assertEqual(pkt[10:16], bytes([0x81, 4, 0, 0x01, 4, 0]))

    def test_long_macro_multi_packet_and_infinite(self):
        recs = [MacroRecord(REC_KEY_DOWN if i % 2 == 0 else REC_KEY_UP, 4 + i // 2) for i in range(20)]
        self.k.set_macro(KeyMacro(key=0x3A, name="x", cycles=MACRO_INFINITE, interval_ms=500, records=recs))
        ws = [w[1:] for w in self.dev.writes if w[1] == retro87.CMD_SET_MACRO]
        data = b"".join(r.pack() for r in recs) + bytes([REC_DELAY, 0xF4, 0x01, 0])
        self.assertEqual(ws[0][:6], bytes([retro87.CMD_SET_MACRO, 0x3A, 1, 0, 0, 25]))
        self.assertEqual(ws[0][6:10], bytes([1, 0, 0x20, len(data) // 3]))
        self.assertEqual(ws[0][10:31], data[:21])
        self.assertEqual(ws[1][:6], bytes([retro87.CMD_SET_MACRO, 0x3A, 1, 25, 0, 24]))
        self.assertEqual(ws[1][6:30], data[21:45])
        self.assertEqual(ws[-1][2], 0)  # last packet: more = 0
        joined = b"".join(w[6:6 + w[5]] for w in ws[1:])
        self.assertEqual(joined, data[21:])

    def test_macro_parse(self):
        raw = bytes([1, 3, 0, 4, 0x81, 4, 0, 0x01, 4, 0, 0x0F, 0x2C, 0x01, 0x0F, 0x64, 0x00]) + bytes(600)
        chunks = []
        off = 0
        while off < len(raw):
            part = raw[off:off + 26]
            more = 1 if off + 26 < 609 else 0
            chunks.append(bytes([retro87.REPORT_IN, retro87.CMD_GET_MACRO, 0, more, 0, 0, 0]) + part)
            off += 26
        name = bytes([retro87.REPORT_IN, retro87.CMD_GET_MACRO_NAME, 0, 0, 0]) + "hi".encode("utf-16-be") + bytes(24)

        def respond(buf):
            if buf[1] == retro87.CMD_GET_MACRO:
                return chunks
            if buf[1] == retro87.CMD_GET_MACRO_NAME:
                return [name]
            return []
        k = Retro87(FakeHidraw(respond))
        m = k.get_macro(0x47)
        self.assertEqual(m.name, "hi")
        self.assertEqual(m.cycles, 3)
        # the trailing delay record is the repeat interval
        self.assertEqual(m.interval_ms, 100)
        self.assertEqual(m.records, [MacroRecord(REC_KEY_DOWN, 4), MacroRecord(REC_KEY_UP, 4), MacroRecord(REC_DELAY, 300)])


if __name__ == "__main__":
    unittest.main()
