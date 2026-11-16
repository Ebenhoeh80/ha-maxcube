"""Constants for the eQ-3 MAX! Cube integration."""

from __future__ import annotations

DOMAIN = "maxcube"

DEFAULT_PORT = 62910
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 600

CONF_SCAN_INTERVAL = "scan_interval"

MANUFACTURER = "eQ-3"

# maxcube-api device type ids -> human readable model names.
DEVICE_TYPE_NAMES: dict[int, str] = {
    0: "MAX! Cube",
    1: "Radiator Thermostat",
    2: "Radiator Thermostat+",
    3: "Wall Thermostat",
    4: "Window/Door Contact",
    5: "Eco Button",
}
