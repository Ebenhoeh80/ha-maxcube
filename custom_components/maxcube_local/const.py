"""Constants for the eQ-3 MAX! Cube integration."""

from __future__ import annotations

DOMAIN = "maxcube_local"

DEFAULT_PORT = 62910
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 600

CONF_SCAN_INTERVAL = "scan_interval"
CONF_CUBE_SERIAL = "cube_serial"
# Version 1.2 of an entry is identified by the Cube's serial number (earlier: by its address).
CONFIG_ENTRY_MINOR_VERSION = 2
TITLE_PREFIX = "MAX! Cube"

SERVICE_RECONNECT = "reconnect"
SERVICE_COPY_SCHEDULE = "copy_schedule"
# A programme is not written when the Cube has already used this share of its radio time.
MAX_DUTY_CYCLE_FOR_WRITING = 90  # percent
# The Cube shows a new programme only after the thermostat has taken it (about two minutes in
# practice), so a write is checked again after this long.
SCHEDULE_VERIFY_DELAY = 300  # seconds
# After a failed poll the integration looks for the Cube under a new IP address, at most this often.
REDISCOVER_COOLDOWN = 300  # seconds
# A poll is repeated once if the Cube refused or dropped the connection (another client such as the
# MAX! app can hold its single connection for a moment); a timeout is not repeated, it took long enough.
POLL_RETRY_DELAY = 1.0  # seconds
# After a command the state is read back at once; further read-backs within this time are merged.
# (Home Assistant's default is 10 s, which leaves the second of two quick changes unseen for that long.)
REQUEST_REFRESH_COOLDOWN = 2.0  # seconds

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
