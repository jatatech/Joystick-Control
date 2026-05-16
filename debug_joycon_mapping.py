import os
import sys
import time


ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from Modules.pyjoystick.interface import Key  # noqa: E402
from Modules.pyjoystick.sdl2 import run_event_loop  # noqa: E402


def key_control_name(key):
    control_name = getattr(key, "controller_key_name", None)
    if control_name:
        try:
            return control_name.decode("utf-8")
        except AttributeError:
            return str(control_name)

    joystick = getattr(key, "joystick", None)
    controller_mapping = getattr(joystick, "controller_mapping", {}) or {}
    for mapped_control_name, mapped_key in controller_mapping.items():
        if mapped_key.keytype == key.keytype and mapped_key.number == key.number:
            return str(mapped_control_name)
    return ""


def print_joystick(joy):
    guid = getattr(joy, "guid", b"")
    try:
        guid = guid.decode("utf-8")
    except AttributeError:
        guid = str(guid)

    print("joystick added")
    print("  name:", joy.get_name())
    print("  guid:", guid)
    print("  axes/buttons/hats:", joy.get_numaxes(), joy.get_numbuttons(), joy.get_numhats())
    print("  controller mapping:")
    controller_mapping = getattr(joy, "controller_mapping", {}) or {}
    for control_name in sorted(controller_mapping):
        print("   ", control_name, "->", controller_mapping[control_name])
    print("")


def add_joystick(joy):
    print_joystick(joy)


def remove_joystick(joy):
    print("joystick removed:", joy.get_name())


def handle_key_event(key):
    if key.keytype == Key.AXIS:
        value = "{:.3f}".format(key.get_proper_value())
    else:
        value = str(key.value)

    print(
        "event:",
        "type={}".format(key.keytype),
        "number={}".format(key.number),
        "value={}".format(value),
        "hat={}".format(key.get_hat_name() if key.keytype == Key.HAT else ""),
        "control={}".format(key_control_name(key)),
    )


def alive():
    return True


def main():
    print("Waiting for joystick events. Press Ctrl+C to stop.")
    try:
        run_event_loop(
            add_joystick=add_joystick,
            remove_joystick=remove_joystick,
            handle_key_event=handle_key_event,
            alive=alive,
        )
    except KeyboardInterrupt:
        print("\nStopped.")
        time.sleep(0.05)


if __name__ == "__main__":
    main()