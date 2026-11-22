"""Display setting of a MAX! wall thermostat: the radio message (pure functions, no Home Assistant).

A wall thermostat can show either its setpoint (the default) or the measured room temperature. The
setting is sent as one radio telegram. Its layout follows Bouni/max-cube-protocol (S-Message.md:
command 82 "Enable/disable display of current temperature", only wall thermostats, 04 = actual
temperature, 00 = setpoint) and the official MAX! software 1.4.6 (frame type 0x82 in byte 2, the RF
address in bytes 6-8, the setting in byte 10).

The current setting can not be read back from the Cube: the status bytes of the wall thermostat
that could carry it are not documented reliably, so the integration offers two buttons, not a switch.
"""

from __future__ import annotations

# Frame type of "SwitchDisplaySetPointActual" (byte 2 of the message).
FRAME_TYPE_DISPLAY = "82"
# The setting in byte 10: 04 = show the actual temperature, 00 = show the setpoint.
_SHOW_ACTUAL = "04"
_SHOW_SETPOINT = "00"


def encode_display_setting(rf_address: str, show_actual: bool) -> str:
    """Return the radio message (hex) that sets what a wall thermostat displays.

    Layout: ``00`` (unknown), ``00`` (addressed to a device, not a room), ``82`` (display command), the
    null address, the thermostat's RF address (3 bytes), ``00`` (room id, not sent by the official
    software for this command), and the setting ``04`` (actual) or ``00`` (setpoint).
    """
    setting = _SHOW_ACTUAL if show_actual else _SHOW_SETPOINT
    return "0000" + FRAME_TYPE_DISPLAY + "000000" + rf_address.upper() + "00" + setting
