"""Config flow for the eQ-3 MAX! Cube integration."""

from __future__ import annotations

from typing import Any

from maxcube.cube import MaxCube
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import MaxCubeConfigEntry
from .discovery import discover_cubes


def _try_connect(host: str, port: int) -> None:
    """Blocking connection test, run from the executor."""
    cube = MaxCube(host, port)
    cube.update()


class MaxCubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MAX! Cube."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the Cube's IP is entered."""
        errors: dict[str, str] = {}
        suggested_host = ""
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(_try_connect, host, port)
            except OSError:
                errors["base"] = "cannot_connect"
                suggested_host = host
            else:
                return self.async_create_entry(
                    title=f"MAX! Cube ({host})", data=user_input
                )
        else:
            # First display: broadcast for a Cube to pre-fill the IP address.
            cubes = await self.hass.async_add_executor_job(discover_cubes)
            configured = self._async_current_ids()
            for cube in cubes:
                if cube["host"] not in configured:
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
