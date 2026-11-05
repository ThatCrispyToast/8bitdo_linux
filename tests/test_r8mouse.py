import unittest

from eightbitdo import r8mouse
from eightbitdo.r8mouse import R8Mouse, DpiTable, RateTable, Macro, MacroRecord
from tests.fake_hid import FakeHidraw


def echo_responder(payload_for_cmd=None):
    """Reply to every request with a matching header and optional payload."""
    def respond(buf):
        pkt = buf[1:]  # strip hidraw report id (0)
        cls_, cmd, op = pkt[1], pkt[2], pkt[3]
        payload = (payload_for_cmd or {}).get(cmd, b"")
        rep = bytes([0x21, cls_, cmd, 0x10 | op]) + payload
        return [rep + bytes(64 - len(rep))]
    return respond


class MouseFraming(unittest.TestCase):
    def setUp(self):
        self.dev = FakeHidraw(echo_responder())
        self.m = R8Mouse(self.dev)

    def test_request_layout(self):
        self.m.set_lod(2)
        w = self.dev.writes[-1]
        self.assertEqual(len(w), 65)
        self.assertEqual(w[0], 0)  # no report id on the wire
        self.assertEqual(w[1:6], bytes([0x01, 6, r8mouse.CMD_LOD, r8mouse.OP_WRITE, 2]))

    def test_dpi_packet(self):
        self.m.set_dpi(1, DpiTable(0b000111, [800, 1200, 1600, 2400, 3200, 6400]))
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[:4], bytes([1, 6, r8mouse.CMD_DPI, 4]))
        self.assertEqual(w[4:6], bytes([1, 0b000111]))
        self.assertEqual(w[6:18], bytes([0x20, 3, 0xB0, 4, 0x40, 6, 0x60, 9, 0x80, 12, 0, 25]))

    def test_dpi_range_check(self):
        with self.assertRaises(ValueError):
            self.m.set_dpi(0, DpiTable(63, [10, 800, 800, 800, 800, 800]))

    def test_button_packet(self):
        self.m.set_button(3, 0x1234, 1)
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[:10], bytes([1, 6, r8mouse.CMD_WRITE_MAP, 4, 1, 3, 0x34, 0x12, 0, 0]))
        self.m.set_button(8, 33)
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[:10], bytes([1, 6, r8mouse.CMD_WRITE_MAP, 4, 0, 8, 33, 0, 0, 0]))

    def test_get_buttons_reads_all_eight_positions(self):
        # Replies captured from a Retro R8 (firmware 10.14).  Positions 5/6 are
        # the right-side pair (disabled = 255 from the factory; their entries
        # carry index bytes 9/10, which is why the table is keyed by position),
        # 7/8 are the wheel directions (7 = rolled towards the user, 8 = away).
        replies = {
            1: bytes.fromhex("090102" "000102000000" "000203000000"),
            3: bytes.fromhex("090302" "000305000000" "000404000000"),
            5: bytes.fromhex("090502" "0009ff000000" "000aff000000"),
            7: bytes.fromhex("090702" "000720000000" "000821000000"),
        }

        def respond(buf):
            pkt = buf[1:]
            self.assertEqual(pkt[:5], bytes([1, 6, r8mouse.CMD_READ_MAP, 1, 9]))
            self.assertEqual(pkt[6], 2)
            rep = bytes([0x21, 6, r8mouse.CMD_READ_MAP, 0x11]) + replies[pkt[5]]
            return [rep + bytes(64 - len(rep))]

        dev = FakeHidraw(respond)
        b = R8Mouse(dev).get_buttons()
        self.assertEqual([w[1 + 5] for w in dev.writes], [1, 3, 5, 7])
        self.assertEqual([(x.index, x.function, x.macro_enabled) for x in b],
                         [(1, 2, 0), (2, 3, 0), (3, 5, 0), (4, 4, 0), (5, 255, 0), (6, 255, 0), (7, 32, 0), (8, 33, 0)])
        self.assertEqual(sorted(r8mouse.MACRO_SLOT), [3, 4, 5, 6])

    def test_profile_name_two_chunks(self):
        self.m.set_profile_name("linux")
        ws = [w[1:] for w in self.dev.writes]
        self.assertEqual(len(ws), 2)
        self.assertEqual(ws[0][4:8], bytes([0, 0, 10, 0]))
        self.assertEqual(ws[0][8:18], "linux".encode("utf-16-be"))
        self.assertEqual(ws[1][4:8], bytes([0, 0, 10 | 0x20, 0]))
        self.assertEqual(ws[1][8:18], bytes(10))

    def test_rate_packet_matches_official_dll(self):
        self.m.set_rate(RateTable(6, 2, [250, 500, 1000, 2000, 4000, 8000]))
        w = self.dev.writes[-1][1:]
        self.assertEqual(w[:4], bytes([1, 6, r8mouse.CMD_RATE, 4]))
        self.assertEqual(w[4:10], bytes([6, 2, 0, 0, 0, 0]))
        self.assertEqual(w[10:22], bytes([0xFA, 0, 0xF4, 1, 0xE8, 3, 0xD0, 7, 0xA0, 0x0F, 0x40, 0x1F]))

    def test_assign_macro_order(self):
        # The R8 only latches macro_enable when the map entry (enable=1) is written
        # before the macro blob - the official app's order.
        import unittest.mock as mock
        recs = [MacroRecord(15, 0, 10), MacroRecord(7, 0, 10)]
        with mock.patch.object(r8mouse.time, "sleep"):
            self.m.assign_macro(Macro(button=3, name="ac", cycles=0xFFFF, interval_ms=50, slot=1, records=recs), function=5)
        ws = [w[1:] for w in self.dev.writes]
        self.assertEqual(ws[0][2:10], bytes([r8mouse.CMD_WRITE_MAP, 4, 1, 3, 5, 0, 0, 0]))
        self.assertEqual(ws[1][2:7], bytes([r8mouse.CMD_MACRO, 4, 1, 2, 3]))

    def test_macro_packets(self):
        recs = [MacroRecord(10, 4, 10), MacroRecord(2, 4, 50), MacroRecord(15, 0, 10)]
        self.m.set_macro(Macro(button=3, name="ab", cycles=2, interval_ms=100, slot=1, records=recs))
        ws = [w[1:] for w in self.dev.writes]
        # header, 3 name chunks, 2 data chunks
        self.assertEqual(len(ws), 6)
        self.assertEqual(ws[0][4:15], bytes([1, 3, 3, 2, 0, 1, 0, 0, 0x20, 100, 0]))
        self.assertEqual(ws[1][4:7], bytes([4, 3, 0]))
        self.assertEqual(ws[2][4:7], bytes([4, 3, 8]))
        self.assertEqual(ws[3][4:7], bytes([4, 3, 0x10]))
        data = b"".join(r.pack() for r in recs)
        self.assertEqual(ws[4][4:9], bytes([2, 0, 0, 0, 2]))
        self.assertEqual(ws[4][9:19], data[:10])
        checksum = sum(data)
        self.assertEqual(ws[5][4:9], bytes([3, checksum & 0xFF, checksum >> 8, 2, 1]))
        self.assertEqual(ws[5][9:14], data[10:])

    def test_reply_validation_and_retry(self):
        # wrong command in reply -> no match -> R8Error after retries
        dev = FakeHidraw(lambda buf: [bytes([0x21, 6, 0x99, 0x11]) + bytes(60)])
        m = R8Mouse(dev, retries=2)
        with self.assertRaises(r8mouse.R8Error):
            m.get_lod()
        self.assertEqual(len(dev.writes), 2)

    def test_read_parsing(self):
        payloads = {
            r8mouse.CMD_DPI: bytes([0, 63]) + bytes([0x20, 3, 0xB0, 4, 0x40, 6, 0x60, 9, 0x80, 12, 0, 25]),
            r8mouse.CMD_RATE: bytes([6, 1, 0, 0, 0xFA, 0, 0xF4, 1, 0xE8, 3, 0xD0, 7, 0xA0, 0x0F, 0x40, 0x1F]),
        }
        m = R8Mouse(FakeHidraw(echo_responder(payloads)))
        self.assertEqual(m.get_dpi(0), DpiTable(63, [800, 1200, 1600, 2400, 3200, 6400]))
        self.assertEqual(m.get_rate(), RateTable(6, 1, [250, 500, 1000, 2000, 4000, 8000]))

    def test_get_buttons_stops_at_end_marker(self):
        end = {r8mouse.CMD_READ_MAP: bytes([9, 1, 2, 0, 0xFF, 0, 0, 0, 0, 0, 0xFF, 0, 0, 0, 0])}
        dev = FakeHidraw(echo_responder(end))
        self.assertEqual(R8Mouse(dev).get_buttons(), [])
        self.assertEqual(len(dev.writes), 1)  # an index byte of 255 ends the table


if __name__ == "__main__":
    unittest.main()
