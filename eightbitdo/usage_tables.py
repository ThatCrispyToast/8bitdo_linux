"""Key / button naming tables shared by the keyboard and mouse protocols.

Key names follow a simple convention so they can be typed on a command line:
letters/digits as-is (``a``, ``1``), function keys ``f1``..``f24``, and
descriptive names (``enter``, ``left_ctrl``, ``kp_1`` ...).  Lookups are
case-insensitive and accept a few aliases.
"""
from __future__ import annotations

from typing import Dict, Optional

# --- USB HID Keyboard/Keypad usage page (0x07) --------------------------------
HID_KEY: Dict[str, int] = {
    "none": 0x00,
    "a": 0x04, "b": 0x05, "c": 0x06, "d": 0x07, "e": 0x08, "f": 0x09, "g": 0x0A,
    "h": 0x0B, "i": 0x0C, "j": 0x0D, "k": 0x0E, "l": 0x0F, "m": 0x10, "n": 0x11,
    "o": 0x12, "p": 0x13, "q": 0x14, "r": 0x15, "s": 0x16, "t": 0x17, "u": 0x18,
    "v": 0x19, "w": 0x1A, "x": 0x1B, "y": 0x1C, "z": 0x1D,
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22, "6": 0x23, "7": 0x24,
    "8": 0x25, "9": 0x26, "0": 0x27,
    "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
    "minus": 0x2D, "equal": 0x2E, "left_bracket": 0x2F, "right_bracket": 0x30,
    "backslash": 0x31, "non_us_hash": 0x32, "semicolon": 0x33, "quote": 0x34,
    "grave": 0x35, "comma": 0x36, "period": 0x37, "slash": 0x38, "caps_lock": 0x39,
    "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D, "f5": 0x3E, "f6": 0x3F,
    "f7": 0x40, "f8": 0x41, "f9": 0x42, "f10": 0x43, "f11": 0x44, "f12": 0x45,
    "print_screen": 0x46, "scroll_lock": 0x47, "pause": 0x48, "insert": 0x49,
    "home": 0x4A, "page_up": 0x4B, "delete": 0x4C, "end": 0x4D, "page_down": 0x4E,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "num_lock": 0x53, "kp_slash": 0x54, "kp_asterisk": 0x55, "kp_minus": 0x56,
    "kp_plus": 0x57, "kp_enter": 0x58, "kp_1": 0x59, "kp_2": 0x5A, "kp_3": 0x5B,
    "kp_4": 0x5C, "kp_5": 0x5D, "kp_6": 0x5E, "kp_7": 0x5F, "kp_8": 0x60,
    "kp_9": 0x61, "kp_0": 0x62, "kp_period": 0x63, "non_us_backslash": 0x64,
    "application": 0x65, "power": 0x66, "kp_equal": 0x67,
    "f13": 0x68, "f14": 0x69, "f15": 0x6A, "f16": 0x6B, "f17": 0x6C, "f18": 0x6D,
    "f19": 0x6E, "f20": 0x6F, "f21": 0x70, "f22": 0x71, "f23": 0x72, "f24": 0x73,
    "execute": 0x74, "help": 0x75, "menu": 0x76, "select": 0x77, "stop": 0x78,
    "again": 0x79, "undo": 0x7A, "cut": 0x7B, "copy": 0x7C, "paste": 0x7D,
    "find": 0x7E, "mute": 0x7F, "volume_up": 0x80, "volume_down": 0x81,
    "left_ctrl": 0xE0, "left_shift": 0xE1, "left_alt": 0xE2, "left_gui": 0xE3,
    "right_ctrl": 0xE4, "right_shift": 0xE5, "right_alt": 0xE6, "right_gui": 0xE7,
}

KEY_ALIASES: Dict[str, str] = {
    "escape": "esc", "return": "enter", "spacebar": "space", "del": "delete",
    "ins": "insert", "pgup": "page_up", "pgdn": "page_down", "pgdown": "page_down",
    "prtsc": "print_screen", "printscreen": "print_screen", "sysrq": "print_screen",
    "scrlk": "scroll_lock", "capslock": "caps_lock", "numlock": "num_lock",
    "lctrl": "left_ctrl", "lshift": "left_shift", "lalt": "left_alt",
    "lwin": "left_gui", "lgui": "left_gui", "lsuper": "left_gui", "lmeta": "left_gui",
    "rctrl": "right_ctrl", "rshift": "right_shift", "ralt": "right_alt",
    "rwin": "right_gui", "rgui": "right_gui", "rsuper": "right_gui", "rmeta": "right_gui",
    "ctrl": "left_ctrl", "shift": "left_shift", "alt": "left_alt", "win": "left_gui",
    "super": "left_gui", "gui": "left_gui", "meta": "left_gui",
    "tilde": "grave", "backtick": "grave", "apostrophe": "quote",
    "lbracket": "left_bracket", "rbracket": "right_bracket", "[": "left_bracket",
    "]": "right_bracket", "\\": "backslash", ";": "semicolon", "'": "quote",
    "`": "grave", ",": "comma", ".": "period", "/": "slash", "-": "minus", "=": "equal",
    "kp_divide": "kp_slash", "kp_multiply": "kp_asterisk", "kp_dot": "kp_period",
    "kp_decimal": "kp_period", "kp_add": "kp_plus", "kp_subtract": "kp_minus",
    "up_arrow": "up", "down_arrow": "down", "left_arrow": "left", "right_arrow": "right",
    "app": "application", "compose": "application", "context_menu": "application",
}

HID_KEY_NAME: Dict[int, str] = {v: k for k, v in HID_KEY.items()}

MODIFIER_CODES = {0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7}


def normalize_key(name: str) -> str:
    n = name.strip().lower().replace("-", "_").replace(" ", "_")
    if n.startswith("kp") and not n.startswith("kp_") and len(n) > 2:
        n = "kp_" + n[2:]
    return KEY_ALIASES.get(n, n)


def key_code(name: str) -> Optional[int]:
    """HID usage code for a key name, or None."""
    n = normalize_key(name)
    if n in HID_KEY:
        return HID_KEY[n]
    if n.startswith("0x"):
        try:
            return int(n, 16)
        except ValueError:
            return None
    return None


def key_name(code: int) -> str:
    return HID_KEY_NAME.get(code, f"0x{code:02x}")


# --- Consumer page (0x0C) usages used by the keyboard's media/shortcut mapping --
CONSUMER: Dict[str, int] = {
    "volume_down": 0x00EA,
    "volume_up": 0x00E9,
    "mute": 0x00E2,
    "play_pause": 0x00CD,
    "prev_track": 0x00B6,
    "next_track": 0x00B5,
    "mail": 0x018A,
    "calculator": 0x0192,
    "my_computer": 0x08E3,   # value the official app sends for "Computer"
    "browser_home": 0x0223,  # official app calls this "Explorer"
    "brightness_down": 0x0070,
    "brightness_up": 0x006F,
}
CONSUMER_NAME: Dict[int, str] = {v: k for k, v in CONSUMER.items()}
CONSUMER_ALIASES: Dict[str, str] = {
    "vol_down": "volume_down", "vol_up": "volume_up", "voldown": "volume_down",
    "volup": "volume_up", "play": "play_pause", "pause_play": "play_pause",
    "previous": "prev_track", "prev": "prev_track", "next": "next_track",
    "calc": "calculator", "computer": "my_computer", "explorer": "browser_home",
    "home_page": "browser_home", "bright_down": "brightness_down",
    "bright_up": "brightness_up",
}

# --- Mouse actions (keyboard key -> mouse function) ----------------------------
# Encoded as a 5-byte mouse report: [buttons][x][y][wheel][ac_pan]
MOUSE_ACTION: Dict[str, bytes] = {
    "mouse_left": bytes([0x01, 0, 0, 0, 0]),
    "mouse_right": bytes([0x02, 0, 0, 0, 0]),
    "mouse_middle": bytes([0x04, 0, 0, 0, 0]),
    "mouse_forward": bytes([0x08, 0, 0, 0, 0]),   # button 5  ("Five" in the app)
    "mouse_back": bytes([0x10, 0, 0, 0, 0]),      # button 4  ("Four" in the app)
    "mouse_double_click": bytes([0x80, 0, 0, 0, 0]),
    "scroll_up": bytes([0, 0, 0, 0x02, 0]),
    "scroll_down": bytes([0, 0, 0, 0xFE, 0]),
    "scroll_left": bytes([0, 0, 0, 0, 0xFE]),
    "scroll_right": bytes([0, 0, 0, 0, 0x02]),
}
MOUSE_ACTION_NAME: Dict[bytes, str] = {v: k for k, v in MOUSE_ACTION.items()}

# --- Retro R8 mouse: button-function enum (u32 "mapping" value) ---------------
# Ordinals come straight from the official software's Mouse_Enum.
R8_FUNCTION: Dict[str, int] = {
    "none": 0,
    "left_click": 1, "right_click": 2, "middle_click": 3,
    "back": 4,            # "button 4"
    "forward": 5,         # "button 5"
    "media_player": 6, "play_pause": 7, "next_track": 8, "prev_track": 9,
    "stop_media": 10, "mute": 11, "volume_up": 12, "volume_down": 13,
    "mail": 14, "calculator": 15, "explorer": 16, "browser_home": 17,
    "browser_search": 18, "browser_forward": 19, "browser_back": 20,
    "browser_stop": 21, "browser_refresh": 22, "browser_favorites": 23,
    "dpi_up": 24, "dpi_down": 25, "dpi_cycle": 26, "rgb_toggle": 27,
    "polling_rate_cycle": 28, "led_mode_cycle": 29,
    "mac_page_up": 30, "mac_page_down": 31,
    # The app's enum calls 32 WHEEL_UP and 33 WHEEL_DOWN, but 32 sends HID wheel -1
    # (scroll down) and 33 wheel +1 (captured on hardware); named by what they do.
    "scroll_down": 32, "scroll_up": 33, "scroll_left": 34, "scroll_right": 35,
    "double_click": 36, "aim": 37, "fire": 38,
    "r4": 39, "r5": 40, "wheel_button": 41, "motion_button": 42, "pair": 43,
    "ble_mode": 44, "2p4g_mode": 45,
    "mac_search": 46, "mac_screenshot": 47, "mac_desktop": 48, "mac_show_dock": 49,
    "mac_input_method": 50, "mac_control_center": 51, "mac_app_window": 52,
    "mac_brightness_up": 53, "mac_brightness_down": 54, "mac_next_desktop": 55,
    "mac_prev_desktop": 56, "mac_narrator": 57,
    "ml": 58, "mr": 59,
    "select_all": 60, "new": 61, "open": 62, "save": 63, "cut": 64, "copy": 65,
    "paste": 66, "undo": 67, "redo": 68, "zoom_in": 69, "zoom_out": 70,
    "shift_left_bracket": 71, "shift_right_bracket": 72, "shift_backslash": 73,
    "shift_semicolon": 74, "shift_quote": 75, "shift_period": 76, "shift_comma": 77,
    "shift_slash": 78, "custom": 79,
    "win_lock_screen": 80, "win_show_desktop": 81, "win_my_computer": 82,
    "win_default_browser": 83, "win_screenshot_tool": 84, "win_face_tool": 85,
    "win_switch_app": 86, "win_close_app": 87, "win_brightness_up": 88,
    "win_brightness_down": 89, "win_minimize_window": 90, "win_run": 91,
    "win_task_manager": 92, "win_settings": 93, "win_search": 94,
    "mute_2": 95, "mic": 96, "mode": 97, "channel_up": 98, "channel_down": 99,
    "voice_assistant": 100, "voice_assistant_stop": 101, "voice_assistant_long": 102,
    "custom_m": 103, "custom_m_long": 104, "custom_ai": 105, "custom_ai_long": 106,
    "custom_pair": 107, "voice_assistant_timeout": 108,
    "num_lock": 109, "kp_slash": 110, "kp_asterisk": 111, "kp_minus": 112,
    "kp_plus": 113, "kp_1": 114, "kp_2": 115, "kp_3": 116, "kp_4": 117, "kp_5": 118,
    "kp_6": 119, "kp_7": 120, "kp_8": 121, "kp_9": 122, "kp_0": 123, "kp_period": 124,
    "kp_enter": 125, "custom_2": 126, "menu": 127,
    "a": 128, "b": 129, "c": 130, "d": 131, "e": 132, "f": 133, "g": 134, "h": 135,
    "i": 136, "j": 137, "k": 138, "l": 139, "n": 140, "m": 141, "o": 142, "p": 143,
    "q": 144, "r": 145, "x": 146, "t": 147, "u": 148, "v": 149, "w": 150, "s": 151,
    "y": 152, "z": 153,
    "1": 154, "2": 155, "3": 156, "4": 157, "5": 158, "6": 159, "7": 160, "8": 161,
    "9": 162, "0": 163,
    "f1": 164, "f2": 165, "f3": 166, "f4": 167, "f5": 168, "f6": 169, "f7": 170,
    "f8": 171, "f9": 172, "f10": 173, "f11": 174, "f12": 175,
    "esc": 176, "tab": 177, "caps_lock": 178, "space": 179, "up": 180, "down": 181,
    "left": 182, "right": 183, "enter": 184, "backspace": 185, "minus": 186,
    "equal": 187, "left_bracket": 188, "right_bracket": 189, "backslash": 190,
    "semicolon": 191, "quote": 192, "period": 193, "comma": 194, "slash": 195,
    "insert": 196, "delete": 197, "page_up": 198, "page_down": 199,
    "left_gui": 200, "right_gui": 201, "left_alt": 202, "right_alt": 203,
    "left_shift": 204, "right_shift": 205, "left_ctrl": 206, "right_ctrl": 207,
    "sharp": 208, "grave": 209, "fn": 210, "home": 211, "end": 212,
    "print_screen": 213, "scroll_lock": 214, "pause": 215, "kb_mode": 216,
    "kb_search": 217, "kb_go": 218, "kp_enter_2": 219,
    "shift_1": 220, "shift_2": 221, "shift_3": 222, "shift_4": 223, "shift_5": 224,
    "shift_6": 225, "shift_7": 226, "shift_8": 227, "shift_9": 228, "shift_0": 229,
    "shift_grave": 230, "shift_minus": 231, "shift_equal": 232,
    "sleep": 233, "brightness_up": 234, "brightness_down": 235,
    "capture_game_screen": 236, "fetch_chatgpt": 237, "task_window": 238,
    "mic_mute": 239, "macro_recording": 240,
    "f13": 241, "f14": 242, "f15": 243, "f16": 244, "f17": 245, "f18": 246,
    "f19": 247, "f20": 248, "f21": 249, "f22": 250, "f23": 251, "f24": 252,
    "disabled": 255,      # the button does nothing (factory state of right_front/right_back)
}
R8_FUNCTION_NAME: Dict[int, str] = {v: k for k, v in R8_FUNCTION.items()}

# Remappable inputs of the R8: the position in the firmware's button table, which
# is also the index byte a write takes.  3/4 are the thumb-side pair (forward /
# back by default), 5/6 the pair on the other side (the official app's "R4"/"R5",
# disabled from the factory), 7 the wheel rolled towards the user (down) and 8
# the wheel rolled away (up) - confirmed with a HID capture, see PROTOCOL.md.
R8_BUTTON: Dict[str, int] = {
    "left": 0, "right": 1, "middle": 2, "side_front": 3, "side_back": 4,
    "right_front": 5, "right_back": 6, "wheel_down": 7, "wheel_up": 8,
}
R8_BUTTON_NAME: Dict[int, str] = {v: k for k, v in R8_BUTTON.items()}
R8_BUTTON_ALIASES: Dict[str, str] = {
    "btn4": "side_front", "button4": "side_front", "four": "side_front",
    "btn5": "side_back", "button5": "side_back", "five": "side_back",
    "wheel": "middle", "mid": "middle",
    # the official app calls the second pair R4 / R5 ("right 4/5")
    "r4": "right_front", "r5": "right_back",
}
# Buttons that can carry a macro -> storage slot ("num" in the official app).
R8_MACRO_SLOT: Dict[int, int] = {3: 1, 4: 2, 5: 3, 6: 4}


def r8_button_index(name: str) -> Optional[int]:
    n = name.strip().lower().replace("-", "_")
    n = R8_BUTTON_ALIASES.get(n, n)
    if n in R8_BUTTON:
        return R8_BUTTON[n]
    if n.isdigit() and int(n) in R8_BUTTON_NAME:
        return int(n)
    return None


def r8_function_value(name: str) -> Optional[int]:
    n = name.strip().lower().replace("-", "_")
    n = KEY_ALIASES.get(n, n)
    if n in ("unused", "disabled"):
        return 255
    if n in R8_FUNCTION:
        return R8_FUNCTION[n]
    if n.isdigit() and 0 <= int(n) <= 255:
        return int(n)
    return None


# Coarse groups for presenting R8_FUNCTION in a UI (by value range).
R8_GROUPS = [
    (1, 5, "Mouse buttons"), (6, 23, "Media & browser"), (24, 29, "DPI & device"), (30, 31, "Mac"),
    (32, 36, "Scroll & double click"), (37, 38, "Gaming"), (39, 45, "Device"), (46, 57, "Mac shortcuts"),
    (58, 59, "Other"), (60, 70, "Editing shortcuts"), (71, 78, "Symbols"), (79, 79, "Other"),
    (80, 94, "Windows shortcuts"), (95, 108, "Other"), (109, 125, "Keypad"), (126, 127, "Other"),
    (128, 175, "Letters, digits & F-keys"), (176, 219, "Keys & modifiers"), (220, 232, "Symbols"),
    (233, 240, "Other"), (241, 252, "F13 - F24"),
]


def r8_function_group(value: int) -> str:
    if value in (0, 255):
        return "None"
    for lo, hi, name in R8_GROUPS:
        if lo <= value <= hi:
            return name
    return "Other"
