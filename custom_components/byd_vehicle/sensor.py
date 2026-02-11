"""Sensors for BYD Vehicle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    BydDataUpdateCoordinator,
    BydGpsUpdateCoordinator,
    expand_metrics,
    extract_raw,
    get_vehicle_display,
)

_UNIT_HINTS: dict[str, str] = {
    "percent": PERCENTAGE,
    "mileage": "km",
    "endurance": "km",
    "speed": "km/h",
    "temp": "C",
    "pressure": "bar",
    "direction": "deg",
}


@dataclass(frozen=True)
class BydSensorDescription:
    """Description for explicit BYD sensors."""

    key: str
    name: str
    source_key: str
    category: str
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None


EXPLICIT_SENSORS: list[BydSensorDescription] = [
    BydSensorDescription(
        key="elec_percent",
        name="Battery",
        source_key="realtime",
        category="realtime",
        unit=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="endurance_mileage",
        name="Range",
        source_key="realtime",
        category="realtime",
        unit=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="total_mileage",
        name="Odometer",
        source_key="realtime",
        category="realtime",
        unit=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="speed",
        name="Speed",
        source_key="realtime",
        category="realtime",
        unit=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="temp_in_car",
        name="Cabin temperature",
        source_key="realtime",
        category="realtime",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="left_front_tire_pressure",
        name="Left front tire pressure",
        source_key="realtime",
        category="realtime",
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="right_front_tire_pressure",
        name="Right front tire pressure",
        source_key="realtime",
        category="realtime",
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="left_rear_tire_pressure",
        name="Left rear tire pressure",
        source_key="realtime",
        category="realtime",
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="right_rear_tire_pressure",
        name="Right rear tire pressure",
        source_key="realtime",
        category="realtime",
        unit=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="total_energy",
        name="Total energy",
        source_key="energy",
        category="energy",
    ),
    BydSensorDescription(
        key="avg_energy_consumption",
        name="Average energy consumption",
        source_key="energy",
        category="energy",
    ),
    BydSensorDescription(
        key="electricity_consumption",
        name="Electricity consumption",
        source_key="energy",
        category="energy",
    ),
    BydSensorDescription(
        key="fuel_consumption",
        name="Fuel consumption",
        source_key="energy",
        category="energy",
    ),
    BydSensorDescription(
        key="soc",
        name="Charging SOC",
        source_key="charging",
        category="charging",
        unit=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BydSensorDescription(
        key="charging_state",
        name="Charging state",
        source_key="charging",
        category="charging",
    ),
    BydSensorDescription(
        key="connect_state",
        name="Charger connection",
        source_key="charging",
        category="charging",
    ),
    BydSensorDescription(
        key="ac_switch",
        name="AC switch",
        source_key="hvac",
        category="hvac",
    ),
    BydSensorDescription(
        key="temp_out_car",
        name="Exterior temperature",
        source_key="hvac",
        category="hvac",
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
]

EXPLICIT_FIELDS_BY_SOURCE: dict[str, set[str]] = {
    "realtime": {
        desc.key for desc in EXPLICIT_SENSORS if desc.source_key == "realtime"
    },
    "energy": {
        desc.key for desc in EXPLICIT_SENSORS if desc.source_key == "energy"
    },
    "hvac": {
        desc.key for desc in EXPLICIT_SENSORS if desc.source_key == "hvac"
    },
    "charging": {
        desc.key for desc in EXPLICIT_SENSORS if desc.source_key == "charging"
    },
    "vehicle": set(),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BydDataUpdateCoordinator = data["coordinator"]
    gps_coordinator: BydGpsUpdateCoordinator = data["gps_coordinator"]

    entities: list[SensorEntity] = []

    vehicle_map = coordinator.data.get("vehicles", {})

    for vin, vehicle in vehicle_map.items():
        for description in EXPLICIT_SENSORS:
            active_coordinator = (
                coordinator
                if description.source_key != "gps"
                else gps_coordinator
            )
            entities.append(
                BydTelemetrySensor(
                    active_coordinator,
                    vin,
                    vehicle,
                    description,
                )
            )
        for category, source_key, source in (
            ("vehicle", "vehicle", vehicle_map),
            ("realtime", "realtime", coordinator.data.get("realtime", {})),
            ("energy", "energy", coordinator.data.get("energy", {})),
            ("hvac", "hvac", coordinator.data.get("hvac", {})),
            ("charging", "charging", coordinator.data.get("charging", {})),
        ):
            metrics = (
                expand_metrics(source.get(vin)) if source.get(vin) is not None else {}
            )
            for field in metrics:
                if field in EXPLICIT_FIELDS_BY_SOURCE.get(source_key, set()):
                    continue
                entities.append(
                    BydMetricSensor(
                        coordinator if source_key != "gps" else gps_coordinator,
                        vin,
                        vehicle,
                        category,
                        field,
                        source_key,
                    )
                )

    async_add_entities(entities)


class BydTelemetrySensor(CoordinatorEntity, SensorEntity):
    """Representation of a BYD sensor with explicit metadata."""

    def __init__(
        self,
        coordinator: BydDataUpdateCoordinator | BydGpsUpdateCoordinator,
        vin: str,
        vehicle: Any,
        description: BydSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._vin = vin
        self._vehicle = vehicle
        self.entity_description = description
        self._attr_unique_id = f"{vin}_{description.source_key}_{description.key}"
        self._attr_name = (
            f"{get_vehicle_display(vehicle)} {description.name}".replace("_", " ")
        )
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> Any:
        source = (
            self.coordinator.data.get("vehicles", {})
            if self.entity_description.source_key == "vehicle"
            else self.coordinator.data.get(self.entity_description.source_key, {})
        )
        metrics = (
            expand_metrics(source.get(self._vin))
            if source.get(self._vin) is not None
            else {}
        )
        return metrics.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "vin": self._vin,
            "category": self.entity_description.category,
            "field": self.entity_description.key,
        }
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=get_vehicle_display(self._vehicle),
            manufacturer=self._vehicle.brand_name or "BYD",
            model=self._vehicle.model_name or None,
        )


class BydMetricSensor(CoordinatorEntity, SensorEntity):
    """Representation of a BYD vehicle metric."""

    def __init__(
        self,
        coordinator: BydDataUpdateCoordinator | BydGpsUpdateCoordinator,
        vin: str,
        vehicle: Any,
        category: str,
        field: str,
        source_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._vin = vin
        self._vehicle = vehicle
        self._category = category
        self._field = field
        self._source_key = source_key
        self._attr_unique_id = f"{vin}_{category}_{field}"
        self._attr_name = f"{get_vehicle_display(vehicle)} {category} {field}".replace(
            "_", " "
        )

    @property
    def native_value(self) -> Any:
        if self._source_key == "vehicle":
            source = self.coordinator.data.get("vehicles", {})
        else:
            source = self.coordinator.data.get(self._source_key, {})
        metrics = (
            expand_metrics(source.get(self._vin))
            if source.get(self._vin) is not None
            else {}
        )
        return metrics.get(self._field)

    @property
    def native_unit_of_measurement(self) -> str | None:
        for hint, unit in _UNIT_HINTS.items():
            if hint in self._field:
                return unit
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._source_key == "vehicle":
            source = self.coordinator.data.get("vehicles", {})
        else:
            source = self.coordinator.data.get(self._source_key, {})
        raw = (
            extract_raw(source.get(self._vin))
            if source.get(self._vin) is not None
            else None
        )
        attrs: dict[str, Any] = {
            "vin": self._vin,
            "category": self._category,
            "field": self._field,
        }
        if raw:
            attrs["raw"] = raw
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            name=get_vehicle_display(self._vehicle),
            manufacturer=self._vehicle.brand_name or "BYD",
            model=self._vehicle.model_name or None,
        )
