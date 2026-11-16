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
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_HALVES, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity

PRESET_ON = "on"

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


class MaxCubeClimate(MaxCubeEntity, ClimateEntity):
    """A MAX! radiator or wall thermostat."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_HALVES
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

    @property
    def current_temperature(self) -> float | None:
        """Return the measured temperature, if the device reports one."""
        temp = self._device.actual_temperature
        # Radiator thermostats report 0 until they have measured at least once.
        return temp if temp else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._device.target_temperature

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
