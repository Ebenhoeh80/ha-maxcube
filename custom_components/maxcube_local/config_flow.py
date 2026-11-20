"""Config flow for the eQ-3 MAX! Cube integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from maxcube.cube import MaxCube
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_CUBE_SERIAL,
    CONF_SCAN_INTERVAL,
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import MaxCubeConfigEntry
from .discovery import discover_cubes
from .identity import cube_title

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

_LOGGER = logging.getLogger(__name__)


def _try_connect(host: str, port: int) -> str | None:
    """Blocking connection test, run from the executor; returns the Cube's serial number.

    The connection is closed again: the Cube accepts only one client at a time.
    """
    cube = MaxCube(host, port)
    try:
        cube.update()
        return cube.serial
    finally:
        cube.disconnect()


class MaxCubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MAX! Cube."""

    VERSION = 1
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the Cube's IP is entered."""
        errors: dict[str, str] = {}
        suggested_host = ""
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            serial: str | None = None
            try:
                serial = await self.hass.async_add_executor_job(_try_connect, host, port)
            except OSError:
                pass
            except Exception:  # noqa: BLE001 - shown to the user as an unknown error
                _LOGGER.exception("Unexpected error while connecting to the MAX! Cube")
                errors["base"] = "unknown"
            if errors:
                suggested_host = host
            elif not serial:
                errors["base"] = "cannot_connect"
                suggested_host = host
            else:
                # The Cube is identified by its serial number, never by the address it was found at.
                # (Another flow for the same Cube, for example a discovery, does not block adding it here.)
                await self.async_set_unique_id(serial, raise_on_progress=False)
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: host, CONF_PORT: port}, reload_on_update=False
                )
                self._abort_if_known(serial, host)
                return self.async_create_entry(
                    title=cube_title(serial),
                    data={CONF_HOST: host, CONF_PORT: port, CONF_CUBE_SERIAL: serial},
                )
        else:
            # First display: broadcast for a Cube to pre-fill the IP address.
            cubes = await self.hass.async_add_executor_job(discover_cubes)
            for cube in cubes:
                if self._known_entry(cube["serial"], cube["host"]) is None:
                    suggested_host = cube["host"]
                    break

        host_field = (
            vol.Required(CONF_HOST, default=suggested_host)
            if suggested_host
            else vol.Required(CONF_HOST)
        )
        schema = vol.Schema(
            {
                host_field: str,
                vol.Required(
                    CONF_PORT,
                    default=(user_input or {}).get(CONF_PORT, DEFAULT_PORT),
                ): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    def _known_entry(self, serial: str, host: str) -> ConfigEntry | None:
        """Return an entry that already manages this Cube but is not yet identified by its serial number.

        Entries created by versions up to 1.3.2 have the address as their unique id until they are
        migrated (at the next setup); they must not be offered or added a second time.
        """
        entry = self._entry_with_serial(serial)
        if entry is not None:
            return entry
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_CUBE_SERIAL) is None and entry.data.get(CONF_HOST) == host:
                return entry
        return None

    def _entry_with_serial(self, serial: str) -> ConfigEntry | None:
        """Return the entry that is known to manage the Cube with this serial number."""
        for entry in self._async_current_entries(include_ignore=False):
            if serial in (entry.unique_id, entry.data.get(CONF_CUBE_SERIAL)):
                return entry
        return None

    def _abort_if_known(self, serial: str, host: str) -> None:
        """Abort if an entry that is not migrated yet manages this Cube (keeping its address up to date)."""
        known = self._known_entry(serial, host)
        if known is None:
            return
        if known.data.get(CONF_CUBE_SERIAL) == serial and known.data.get(CONF_HOST) != host:
            # The same Cube under a new address; the update listener reloads the entry.
            self.hass.config_entries.async_update_entry(known, data={**known.data, CONF_HOST: host})
        raise AbortFlow("already_configured")

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle a Cube found by the integration's own broadcast scan."""
        return await self._async_handle_discovery(
            discovery_info[CONF_CUBE_SERIAL], discovery_info[CONF_HOST]
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle a device whose hardware address belongs to eQ-3 (a Cube, or another eQ-3 device).

        Home Assistant sees the DHCP request of a Cube when it starts or gets a new address, so this
        finds the first Cube and follows a Cube whose address changed.
        """
        host = discovery_info.ip
        try:
            serial = await self.hass.async_add_executor_job(_try_connect, host, DEFAULT_PORT)
        except Exception:  # noqa: BLE001 - another eQ-3 device, or the Cube is busy
            return self.async_abort(reason="cannot_connect")
        if not serial:
            return self.async_abort(reason="cannot_connect")
        return await self._async_handle_discovery(serial, host)

    async def _async_handle_discovery(self, serial: str, host: str) -> ConfigFlowResult:
        """A Cube answered at ``host``: update the address of a known Cube, or offer a new one.

        The update listener of the entry reloads it; the flow does not reload (``reload_on_update=False``).
        An entry that has no serial number yet is matched by its address only and left unchanged: another
        Cube may have taken that address, the migration at its next setup settles it.
        """
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host}, reload_on_update=False)
        known = self._known_entry(serial, host)
        if known is not None:
            if known.data.get(CONF_CUBE_SERIAL) == serial and known.data.get(CONF_HOST) != host:
                self.hass.config_entries.async_update_entry(
                    known, data={**known.data, CONF_HOST: host}
                )
            return self.async_abort(reason="already_configured")
        self._discovered = {CONF_HOST: host, CONF_CUBE_SERIAL: serial}
        self.context["title_placeholders"] = {"name": cube_title(serial)}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to add a discovered Cube."""
        serial = self._discovered[CONF_CUBE_SERIAL]
        if user_input is not None:
            return self.async_create_entry(
                title=cube_title(serial),
                data={
                    CONF_HOST: self._discovered[CONF_HOST],
                    CONF_PORT: DEFAULT_PORT,
                    CONF_CUBE_SERIAL: serial,
                },
            )
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"serial": serial, "host": self._discovered[CONF_HOST]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: MaxCubeConfigEntry,
    ) -> MaxCubeOptionsFlow:
        """Return the options flow handler."""
        return MaxCubeOptionsFlow()


class MaxCubeOptionsFlow(OptionsFlow):
    """Handle MAX! Cube options (the poll interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll-interval option."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
