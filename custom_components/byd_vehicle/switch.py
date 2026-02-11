"""Switches for BYD Vehicle."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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

    entities: list[SwitchEntity] = []

    vehicle_map = coordinator.data.get("vehicles", {})
    for vin, vehicle in vehicle_map.items():
        entities.append(
            BydMomentarySwitch(coordinator, api, vin, vehicle, "flash_lights")
        )
        entities.append(BydMomentarySwitch(coordinator, api, vin, vehicle, "honk_horn"))
        entities.append(
            BydMomentarySwitch(coordinator, api, vin, vehicle, "open_trunk")
        )
        entities.append(
            BydMomentarySwitch(coordinator, api, vin, vehicle, "close_windows")
        )

    async_add_entities(entities)


class BydMomentarySwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a momentary BYD remote command."""

    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: BydDataUpdateCoordinator,
        api: BydApi,
        vin: str,
        vehicle: Any,
        command: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._vin = vin
        self._vehicle = vehicle
        self._command = command
        self._attr_unique_id = f"{vin}_{command}"
        self._attr_name = f"{get_vehicle_display(vehicle)} {command}".replace("_", " ")

    @property
    def is_on(self) -> bool:
        return False

    async def async_turn_on(self, **_: Any) -> None:
        async def _call(client: Any) -> Any:
            method = getattr(client, self._command, None)
            if method is None:
                raise HomeAssistantError(f"Unknown command: {self._command}")
            return await method(self._vin)

        try:
            await self._api.async_call(_call, vin=self._vin, command=self._command)
        except Exception as exc:  # noqa: BLE001
            raise HomeAssistantError(str(exc)) from exc

        self.async_write_ha_state()

    async def async_turn_off(self, **_: Any) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"vin": self._vin, "command": self._command}
        last_result = self._api.get_last_remote_result(self._vin, self._command)
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
