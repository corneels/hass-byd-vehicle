"""Climate control for BYD Vehicle."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
)
from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pybyd.models.hvac import HvacStatus

from .const import DOMAIN
from .coordinator import BydApi, BydDataUpdateCoordinator, get_vehicle_display


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BydDataUpdateCoordinator = data["coordinator"]
    api: BydApi = data["api"]

    entities: list[ClimateEntity] = []

    vehicle_map = coordinator.data.get("vehicles", {})
    for vin, vehicle in vehicle_map.items():
        entities.append(BydClimate(coordinator, api, vin, vehicle))

    async_add_entities(entities)


class BydClimate(CoordinatorEntity, ClimateEntity):
    """Representation of BYD climate control."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF

    def __init__(
        self,
        coordinator: BydDataUpdateCoordinator,
        api: BydApi,
        vin: str,
        vehicle: Any,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._vin = vin
        self._vehicle = vehicle
        self._attr_unique_id = f"{vin}_climate"
        self._attr_name = f"{get_vehicle_display(vehicle)} climate"
        self._last_mode = HVACMode.OFF
        self._last_command: str | None = None

    def _get_hvac_status(self) -> HvacStatus | None:
        hvac_map = self.coordinator.data.get("hvac", {})
        hvac = hvac_map.get(self._vin)
        if isinstance(hvac, HvacStatus):
            return hvac
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        hvac = self._get_hvac_status()
        if hvac is not None:
            return HVACMode.HEAT_COOL if hvac.is_ac_on else HVACMode.OFF
        return self._last_mode

    @property
    def assumed_state(self) -> bool:
        return self._get_hvac_status() is None

    @property
    def current_temperature(self) -> float | None:
        hvac = self._get_hvac_status()
        if hvac is not None and hvac.interior_temp_available:
            return hvac.temp_in_car
        # Fall back to realtime data
        realtime_map = self.coordinator.data.get("realtime", {})
        realtime = realtime_map.get(self._vin)
        if realtime is not None:
            temp = getattr(realtime, "temp_in_car", None)
            if temp is not None and temp != -129:
                return temp
        return None

    @property
    def target_temperature(self) -> float | None:
        hvac = self._get_hvac_status()
        if hvac is not None:
            if hvac.main_setting_temp_new is not None:
                return hvac.main_setting_temp_new
            if hvac.main_setting_temp is not None:
                return float(hvac.main_setting_temp)
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        async def _call(client: Any) -> Any:
            if hvac_mode == HVACMode.OFF:
                return await client.stop_climate(self._vin)
            return await client.start_climate(self._vin)

        try:
            self._last_command = (
                "stop_climate" if hvac_mode == HVACMode.OFF else "start_climate"
            )
            await self._api.async_call(
                _call, vin=self._vin, command=self._last_command
            )
        except Exception as exc:  # noqa: BLE001
            raise HomeAssistantError(str(exc)) from exc

        self._last_mode = hvac_mode
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"vin": self._vin}
        hvac = self._get_hvac_status()
        if hvac is not None:
            attrs["temp_out_car"] = hvac.temp_out_car
            attrs["front_defrost"] = hvac.front_defrost_status
            attrs["steering_wheel_heat"] = hvac.steering_wheel_heat_state
            attrs["main_seat_heat"] = hvac.main_seat_heat_state
            attrs["main_seat_ventilation"] = hvac.main_seat_ventilation_state
            attrs["copilot_seat_heat"] = hvac.copilot_seat_heat_state
            attrs["copilot_seat_ventilation"] = hvac.copilot_seat_ventilation_state
        if self._last_command:
            attrs["last_remote_command"] = self._last_command
            last_result = self._api.get_last_remote_result(
                self._vin, self._last_command
            )
            if last_result:
                attrs["last_remote_result"] = last_result
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=get_vehicle_display(self._vehicle),
            manufacturer=self._vehicle.brand_name or "BYD",
            model=self._vehicle.model_name or None,
        )
