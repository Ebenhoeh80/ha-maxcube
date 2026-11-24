"""Climate platform for eQ-3 MAX! Cube thermostats."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
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
from homeassistant.core import HomeAssistant, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from maxcube.device import (
    MAX_DEVICE_MODE_AUTOMATIC,
    MAX_DEVICE_MODE_BOOST,
    MAX_DEVICE_MODE_MANUAL,
    MAX_DEVICE_MODE_VACATION,
    MaxDevice,
)

from .const import DOMAIN, MAX_DUTY_CYCLE_FOR_WRITING
from .coordinator import MaxCubeConfigEntry, MaxCubeCoordinator
from .entity import MaxCubeEntity, async_add_devices_as_they_appear
from .schedule import (
    WEEK_DAYS,
    ScheduleError,
    plan_request,
    scheduled_temperature,
)
from .snapshot import DeviceState, schedule_as_dict
from .snapshot import Schedule as DeviceSchedule

_PERIODS = vol.All(
    cv.ensure_list,
    [{vol.Required("until"): cv.string, vol.Required("temperature"): vol.Coerce(float)}],
)
_SET_SCHEDULE_SCHEMA = {
    # One programme for all the given days, or (by_day) its own periods for each day.
    vol.Optional("days"): vol.All(cv.ensure_list, [vol.In(WEEK_DAYS)], vol.Length(min=1)),
    vol.Optional("periods"): _PERIODS,
    vol.Optional("by_day"): {vol.In(WEEK_DAYS): _PERIODS},
    vol.Optional("dry_run", default=False): cv.boolean,
}

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


# the Cube accepts one command at a time: the coordinator does the polling
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MaxCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entities (radiator and wall thermostats)."""

    def _climates(
        coordinator: MaxCubeCoordinator, state: DeviceState, device: MaxDevice
    ) -> list[MaxCubeClimate]:
        if state.is_thermostat or state.is_wallthermostat:
            return [MaxCubeClimate(coordinator, state, device)]
        return []

    async_add_devices_as_they_appear(entry, async_add_entities, _climates)
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "get_schedule", None, "async_get_schedule", supports_response=SupportsResponse.ONLY
    )
    platform.async_register_entity_service(
        "set_schedule",
        _SET_SCHEDULE_SCHEMA,
        "async_set_schedule",
        supports_response=SupportsResponse.OPTIONAL,
    )


def _validated_programme(
    days: list[str] | None,
    periods: list[dict[str, Any]] | None,
    by_day: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Validate the request and turn a problem into a translated service error."""
    try:
        return plan_request(days, periods, by_day)
    except ScheduleError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=f"schedule_{err.key}",
            translation_placeholders={"detail": err.detail},
        ) from err


class MaxCubeClimate(MaxCubeEntity, ClimateEntity):
    """A MAX! radiator or wall thermostat."""

    _attr_name = None
    # The names of the presets are translated (``entity.climate.thermostat`` in strings.json).
    _attr_translation_key = "thermostat"
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

    def __init__(
        self, coordinator: MaxCubeCoordinator, state: DeviceState, device: MaxDevice
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, state, device)
        self._attr_unique_id = state.rf_address
        self._last_heating_temperature: float | None = None
        self._remember_heating_temperature(state)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the last real heating setpoint when a poll brings a new snapshot."""
        self._remember_heating_temperature()
        super()._handle_coordinator_update()

    def _remember_heating_temperature(self, state: DeviceState | None = None) -> None:
        """Remember a manual setpoint so ``heat`` can undo ``off`` without losing it."""
        state = state or self._device_state
        temp = state.target_temperature
        if (
            state.mode == MAX_DEVICE_MODE_MANUAL
            and temp is not None
            and temp not in (OFF_TEMPERATURE, ON_TEMPERATURE)
            and self.min_temp <= temp <= self.max_temp
        ):
            self._last_heating_temperature = temp

    def _heating_target(self) -> float:
        """Return the setpoint to restore when heating is switched on again."""
        if self._last_heating_temperature is not None:
            return self._last_heating_temperature
        schedule = schedule_as_dict(self._schedule)
        scheduled = scheduled_temperature(schedule, dt_util.now())
        if scheduled is not None:
            return scheduled
        comfort = self._device_state.comfort_temperature
        if comfort is not None:
            return comfort
        return self.min_temp

    @property
    def min_temp(self) -> float:
        """Return the minimum target temperature."""
        return self._device_state.min_temperature or MIN_TEMPERATURE

    @property
    def max_temp(self) -> float:
        """Return the maximum target temperature."""
        return self._device_state.max_temperature or MAX_TEMPERATURE

    def _measured_temperature(self) -> float | None:
        """Return the measured temperature, if the device reports one."""
        temp = self._device_state.actual_temperature
        # Radiator thermostats report 0 until they have measured at least once.
        return temp if temp else None

    def _target_temperature(self) -> float | None:
        """Return the target temperature."""
        return self._device_state.target_temperature

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
    def _schedule(self) -> DeviceSchedule:
        """The weekly programme: the thermostat's own, or (wall thermostat) that of its room."""
        state = self._device_state
        if state.schedule:
            return state.schedule
        if state.room_id in self.coordinator.data.room_names:
            for other in self.coordinator.data.devices.values():
                if other.room_id == state.room_id and other.schedule:
                    return other.schedule
        return ()

    async def async_get_schedule(self) -> dict[str, Any]:
        """Return the weekly heating programme (service ``get_schedule``)."""
        return schedule_as_dict(self._schedule)

    def _ensure_radio_time_left(self) -> None:
        """Refuse to write while the Cube has used (almost) all of its radio time."""
        duty = self.coordinator.data.duty_cycle
        if duty is not None and duty >= MAX_DUTY_CYCLE_FOR_WRITING:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="schedule_duty_cycle_high",
                translation_placeholders={"duty": str(duty)},
            )

    async def async_set_schedule(
        self,
        days: list[str] | None = None,
        periods: list[dict[str, Any]] | None = None,
        by_day: dict[str, list[dict[str, Any]]] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Write the daily programme of the given days (or of ``by_day``) to a radiator thermostat."""
        if not self._device_state.is_thermostat:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="schedule_radiator_only"
            )
        programme = _validated_programme(days, periods, by_day)
        if dry_run:
            return {"dry_run": True, "would_write": programme}
        self._ensure_radio_time_left()
        results = await self.coordinator.async_write_schedule(self._device, programme)
        failed = [day for day, result in results.items() if result == "failed"]
        if failed:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="schedule_not_written",
                translation_placeholders={"days": ", ".join(failed)},
            )
        return {"result": results}

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the comfort/eco setpoints, the valve position and the weekly programme."""
        state = self._device_state
        attrs: dict[str, Any] = {}
        schedule = self._schedule
        if schedule:
            programme = schedule_as_dict(schedule)
            attrs["schedule"] = programme
            scheduled = scheduled_temperature(programme, dt_util.now())
            if scheduled is not None:
                attrs["scheduled_temperature"] = scheduled
        comfort = state.comfort_temperature
        eco = state.eco_temperature
        valve = state.valve_position
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
        state = self._device_state
        if state.mode == MAX_DEVICE_MODE_MANUAL and state.target_temperature == OFF_TEMPERATURE:
            return HVACMode.OFF
        if state.mode == MAX_DEVICE_MODE_MANUAL:
            return HVACMode.HEAT
        return HVACMode.AUTO

    @property
    def hvac_action(self) -> HVACAction:
        """Return whether the valve is currently calling for heat."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        valve = self._device_state.valve_position or 0
        if valve > 0:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str:
        """Return the current preset."""
        state = self._device_state
        if state.mode == MAX_DEVICE_MODE_BOOST:
            return PRESET_BOOST
        if state.mode == MAX_DEVICE_MODE_VACATION:
            return PRESET_AWAY
        if state.target_temperature == ON_TEMPERATURE:
            return PRESET_ON
        comfort = state.comfort_temperature
        eco = state.eco_temperature
        if comfort and state.target_temperature == comfort:
            return PRESET_COMFORT
        if eco and state.target_temperature == eco:
            return PRESET_ECO
        return PRESET_NONE

    async def async_set_temperature(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Set a new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self._set_target_temperature(temp)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self._set_target_temperature(OFF_TEMPERATURE)
        elif hvac_mode == HVACMode.HEAT:
            # Restore the last real setpoint, not the 4.5 °C the Cube reports while off.
            target = min(max(self._heating_target(), self.min_temp), self.max_temp)
            await self._set_target_temperature(target)
        elif hvac_mode == HVACMode.AUTO:
            await self._set_mode(MAX_DEVICE_MODE_AUTOMATIC)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a new preset mode."""
        state = self._device_state
        if preset_mode == PRESET_BOOST:
            await self._set_mode(MAX_DEVICE_MODE_BOOST)
        elif preset_mode == PRESET_AWAY:
            await self._set_mode(MAX_DEVICE_MODE_VACATION)
        elif preset_mode == PRESET_NONE:
            await self._set_mode(MAX_DEVICE_MODE_AUTOMATIC)
        elif preset_mode == PRESET_ON:
            await self._set_target_temperature(ON_TEMPERATURE)
        elif preset_mode == PRESET_COMFORT:
            comfort = state.comfort_temperature
            if comfort:
                await self._set_target_temperature(comfort)
        elif preset_mode == PRESET_ECO:
            eco = state.eco_temperature
            if eco:
                await self._set_target_temperature(eco)

    async def _set_target_temperature(self, temperature: float) -> None:
        """Send temperature and MANUAL mode in one telegram.

        The library's ``set_target_temperature`` keeps the current mode, so a setpoint sent while
        the thermostat is in AUTO is overwritten by the weekly programme at the next poll. The
        combined command makes OFF, HEAT, plain setpoints and temperature presets stick.
        """
        await self.coordinator.async_cube_command(
            self.coordinator.cube.set_temperature_mode,
            self._device,
            temperature,
            MAX_DEVICE_MODE_MANUAL,
        )
        if (
            temperature not in (OFF_TEMPERATURE, ON_TEMPERATURE)
            and self.min_temp <= temperature <= self.max_temp
        ):
            self._last_heating_temperature = temperature
        await self.coordinator.async_request_refresh()

    async def _set_mode(self, mode: int) -> None:
        await self.coordinator.async_cube_command(
            self.coordinator.cube.set_mode, self._device, mode
        )
        await self.coordinator.async_request_refresh()
