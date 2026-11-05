# Usage

Changes take effect immediately. `8bitdo-cfg list` shows detected devices;
`--device /dev/hidrawN` overrides detection. `8bitdo-cfg udev` prints the udev rule; `--install` installs it unless a rule already grants access.

## Web UI

```sh
8bitdo-cfg ui                          # http://127.0.0.1:8765
8bitdo-cfg ui --port 9000 --no-browser
```

Click a key or button, then edit it in the inspector. Listens on localhost only.

## Keyboard

```sh
8bitdo-cfg keyboard show
8bitdo-cfg keyboard map caps_lock left_ctrl
8bitdo-cfg keyboard map scroll_lock media:play_pause
8bitdo-cfg keyboard map k1 mouse:left
8bitdo-cfg keyboard map f12 shift+f12         # one modifier per remap
8bitdo-cfg keyboard unmap caps_lock
8bitdo-cfg keyboard macro f24 --name copy tap:ctrl+c delay:50 tap:ctrl+v
8bitdo-cfg keyboard macro k2 --name spam --repeat hold --interval 100 tap:space
8bitdo-cfg keyboard macro-clear f24
8bitdo-cfg keyboard volume 3                  # 1..5
8bitdo-cfg keyboard profile-name work
8bitdo-cfg keyboard dump > keyboard.json
8bitdo-cfg keyboard apply keyboard.json
8bitdo-cfg keyboard reset --yes
8bitdo-cfg keyboard keys                      # key names
8bitdo-cfg keyboard targets                   # remap targets
```

**Macros:** up to 8, 200 events each. Steps: `press:KEY`, `release:KEY`,
`tap:KEY`, `tap:ctrl+c`, `delay:MS`. `--repeat` takes a count or `hold`.

**Extra keys:**

| Name | Key |
| --- | --- |
| `key_b`, `key_a` | Red B and A keys (formerly `super_b`, `super_a`) |
| `k1`, `k2` | Super Buttons, port A (`k1` is the A button) |
| `k3`, `k4` | Super Buttons, port B |
| `k5`, `k6` | Super Buttons, port X |
| `k7`, `k8` | Super Buttons, port Y |

## Mouse

```sh
8bitdo-cfg mouse show
8bitdo-cfg mouse dpi 400 800 1600 3200 6400 12800 --enable 1,2,3,4   # 50..26000
8bitdo-cfg mouse dpi-slot 3
8bitdo-cfg mouse rate 1000                    # 250..8000 Hz
8bitdo-cfg mouse lod 1                        # lift-off, 1 or 2 mm
8bitdo-cfg mouse wheel-speed 5                # 0..14
8bitdo-cfg mouse wheel-direction reversed
8bitdo-cfg mouse left-hand on
8bitdo-cfg mouse button side_back play_pause  # `mouse functions` lists all
8bitdo-cfg mouse macro side_back --name dbl click:left delay:80 click:left
8bitdo-cfg mouse macro-off side_back
8bitdo-cfg mouse dump > mouse.json
8bitdo-cfg mouse apply mouse.json
8bitdo-cfg mouse reset --yes
```

**Buttons:** `right`, `middle`, `side_front`, `side_back`, `right_front`,
`right_back`, `wheel_up`, `wheel_down`.

**Macros:** side buttons only, 80 events. Adds `click:BUTTON`. `--repeat hold`
loops until another button is pressed.

## Python API

```python
from eightbitdo.retro87 import Retro87
from eightbitdo.r8mouse import R8Mouse

with Retro87.open() as kb:
    kb.map_key(0x39, 0xE0)        # caps lock -> left ctrl
    print(kb.read_config())

with R8Mouse.open() as m:
    m.set_wheel_speed(5)
```

## Limitations

- USB cable only; 2.4 GHz receivers are untested or unsupported
- No firmware updates
- Keyboard firmware version is unreadable; `bcdDevice` is shown instead
- Keyboard volume level's physical effect is unknown
- Super Button port order comes from the official app, unverified on hardware
