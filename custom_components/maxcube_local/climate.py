"""Climate platform for eQ-3 MAX! Cube thermostats."""

from __future__ import annotations

from typing import Any

from maxcube.device import (
    MAX_DEVICE_MODE_AUTOMATIC,
    MAX_DEVICE_MODE_BOOST,
    MAX_DEVICE_MODE_MANUAL,
    MAX_DEVICE_MODE_VACATION,
    MaxDevice,
)

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity
from .schedule import Schedule, scheduled_temperature

PRESET_ON = "on"

# Home Assistant 2026.11 renamed the temperature members of ClimateEntity to
# native_* (the old names are deprecated and stop working in 2027.11). Older
# versions only know the old names, so the right ones are chosen at import time.
_NATIVE_TEMPERATURES = hasattr(ClimateEntity, "native_current_temperature")

# Special target-temperature values the Cube uses to encode on/off states.
ON_TEMPERATURE = 30.5
OFF_TEMPERATURE = 4.5
MIN_TEMPERATURE = 5.0
MAX_TEMPERATURE = 30.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entities (radiator and wall thermostats)."""
    coordinator = entry.runtime_data
    cube = coordinator.cube
    async_add_entities(
        MaxCubeClimate(coordinator, device)
        for device in cube.devices
        if device.is_thermostat() or device.is_wallthermostat()
    )
    entity_platform.async_get_current_platform().async_register_entity_service(
        "get_schedule", None, "async_get_schedule", supports_response=SupportsResponse.ONLY
    )


class MaxCubeClimate(MaxCubeEntity, ClimateEntity):
    """A MAX! radiator or wall thermostat."""

    _attr_name = None
    # The programme is large and rarely changes: keep it out of the history database.
    _unrecorded_attributes = frozenset({"schedule"})
    if _NATIVE_TEMPERATURES:
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS
    # The Cube reports the measured temperature in 0.1 °C; setpoints are 0.5 °C.
    _attr_precision = PRECISION_TENTHS
    _attr_target_temperature_step = PRECISION_HALVES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT]
    _attr_preset_modes = [
        PRESET_NONE,
        PRESET_BOOST,
        PRESET_COMFORT,
        PRESET_ECO,
        PRESET_AWAY,
        PRESET_ON,
    ]

    def __init__(self, coordinator: MaxCubeCoordinator, device: MaxDevice) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, device)
        self._attr_unique_id = device.rf_address

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature."""
        return self._device.min_temperature or MIN_TEMPERATURE

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature."""
        return self._device.max_temperature or MAX_TEMPERATURE

    def _measured_temperature(self) -> float | None:
        """Return the measured temperature, if the device reports one."""
        temp = self._device.actual_temperature
        # Radiator thermostats report 0 until they have measured at least once.
        return temp if temp else None

    def _target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._device.target_temperature

    if _NATIVE_TEMPERATURES:

        @property
        def native_current_temperature(self) -> float | None:
            """Return the measured temperature in the device's unit."""
            return self._measured_temperature()

        @property
        def native_target_temperature(self) -> float | None:
            """Return the target temperature in the device's unit."""
            return self._target_temperature()

    else:

        @property
        def current_temperature(self) -> float | None:
            """Return the measured temperature."""
            return self._measured_temperature()

        @property
        def target_temperature(self) -> float | None:
            """Return the target temperature."""
            return self._target_temperature()

    @property
    def _schedule(self) -> Schedule:
        """The weekly programme: the thermostat's own, or (wall thermostat) that of its room."""
        schedule = getattr(self._device, "schedule", None)
        if schedule:
            return schedule
        cube = self.coordinator.cube
        room = cube.room_by_id(getattr(self._device, "room_id", None))
        if room is not None:
            for other in cube.devices_by_room(room):
                schedule = getattr(other, "schedule", None)
                if schedule:
                    return schedule
        return {}

    async def async_get_schedule(self) -> dict[str, Any]:
        """Return the weekly heating programme (service ``get_schedule``)."""
        return self._schedule

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the comfort/eco setpoints, the valve position and the weekly programme."""
        device = self._device
        attrs: dict[str, Any] = {}
        schedule = self._schedule
        if schedule:
            attrs["schedule"] = schedule
            scheduled = scheduled_temperature(schedule, dt_util.now())
            if scheduled is not None:
                attrs["scheduled_temperature"] = scheduled
        comfort = getattr(device, "comfort_temperature", None)
        eco = getattr(device, "eco_temperature", None)
        valve = getattr(device, "valve_position", None)
        if comfort is not None:
            attrs["comfort_temperature"] = comfort
        if eco is not None:
            attrs["eco_temperature"] = eco
        if valve is not None:
            attrs["valve_position"] = valve
        return attrs or None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        device = self._device
        if (
            device.mode == MAX_DEVICE_MODE_MANUAL
            and device.target_temperature == OFF_TEMPERATURE
        ):
            return HVACMode.OFF
        if device.mode == MAX_DEVICE_MODE_MANUAL:
            return HVACMode.HEAT
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        """Return whether the valve is currently calling for heat."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        valve = getattr(self._device, "valve_position", 0) or 0
        if valve > 0:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        """Return the current preset."""
        device = self._device
        if device.mode == MAX_DEVICE_MODE_BOOST:
            return PRESET_BOOST
        if device.mode == MAX_DEVICE_MODE_VACATION:
            return PRESET_AWAY
        if device.target_temperature == ON_TEMPERATURE:
            return PRESET_ON
        comfort = getattr(device, "comfort_temperature", None)
        eco = getattr(device, "eco_temperature", None)
        if comfort and device.target_temperature == comfort:
            return PRESET_COMFORT
        if eco and device.target_temperature == eco:
            return PRESET_ECO
        return PRESET_NONE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self._set_target_temperature(temp)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._set_target_temperature(OFF_TEMPERATURE)
        elif hvac_mode == HVACMode.HEAT:
            target = self._device.target_temperature or self.min_temp
            await self._set_target_temperature(max(target, self.min_temp))
        elif hvac_mode == HVACMode.AUTO:
            await self._set_mode(MAX_DEVICE_MODE_AUTOMATIC)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a new preset mode."""
        device = self._device
        if preset_mode == PRESET_BOOST:
            await self._set_mode(MAX_DEVICE_MODE_BOOST)
        elif preset_mode == PRESET_AWAY:
            await self._set_mode(MAX_DEVICE_MODE_VACATION)
        elif preset_mode == PRESET_NONE:
            await self._set_mode(MAX_DEVICE_MODE_AUTOMATIC)
        elif preset_mode == PRESET_ON:
            await self._set_target_temperature(ON_TEMPERATURE)
        elif preset_mode == PRESET_COMFORT:
            comfort = getattr(device, "comfort_temperature", None)
            if comfort:
                await self._set_target_temperature(comfort)
        elif preset_mode == PRESET_ECO:
            eco = getattr(device, "eco_temperature", None)
            if eco:
                await self._set_target_temperature(eco)

    async def _set_target_temperature(self, temperature: float) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.cube.set_target_temperature, self._device, temperature
        )
        await self.coordinator.async_request_refresh()

    async def _set_mode(self, mode: int) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.cube.set_mode, self._device, mode
        )
        await self.coordinator.async_request_refresh()
