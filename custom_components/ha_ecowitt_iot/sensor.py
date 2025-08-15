"""Platform for sensor integration."""

import dataclasses
from typing import Final
import logging
from wittiot import MultiSensorInfo, WittiotDataTypes
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONF_HOST,
    DEGREE,
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="tempinf",
        translation_key="tempinf",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tempf",
        translation_key="tempf",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="feellike",
        translation_key="feellike",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="apparent",
        translation_key="apparent",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dewpoint",
        translation_key="dewpoint",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="tf_co2",
        translation_key="tf_co2",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="humidityin",
        translation_key="humidityin",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    SensorEntityDescription(
        key="humidity",
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    SensorEntityDescription(
        key="humi_co2",
        translation_key="humi_co2",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    SensorEntityDescription(
        key="baromrelin",
        translation_key="baromrelin",
        native_unit_of_measurement=UnitOfPressure.INHG,
        device_class=SensorDeviceClass.PRESSURE,
    ),
    SensorEntityDescription(
        key="baromabsin",
        translation_key="baromabsin",
        native_unit_of_measurement=UnitOfPressure.INHG,
        device_class=SensorDeviceClass.PRESSURE,
    ),
    SensorEntityDescription(
        key="vpd",
        translation_key="vpd",
        native_unit_of_measurement=UnitOfPressure.INHG,
        device_class=SensorDeviceClass.PRESSURE,
    ),
    SensorEntityDescription(
        key="winddir",
        translation_key="winddir",
        icon="mdi:weather-windy",
        native_unit_of_measurement=DEGREE,
    ),
    SensorEntityDescription(
        key="winddir10",
        translation_key="winddir10",
        icon="mdi:weather-windy",
        native_unit_of_measurement=DEGREE,
    ),
    SensorEntityDescription(
        key="windspeedmph",
        translation_key="windspeedmph",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="windgustmph",
        translation_key="windgustmph",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="daywindmax",
        translation_key="daywindmax",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="uv",
        translation_key="uv",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:brightness-5",
    ),
    SensorEntityDescription(
        key="solarradiation",
        translation_key="solarradiation",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="rainratein",
        translation_key="rainratein",
        native_unit_of_measurement=UnitOfVolumetricFlux.INCHES_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="eventrainin",
        translation_key="eventrainin",
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="dailyrainin",
        translation_key="dailyrainin",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="weeklyrainin",
        translation_key="weeklyrainin",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="monthlyrainin",
        translation_key="monthlyrainin",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="yearlyrainin",
        translation_key="yearlyrainin",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="totalrainin",
        translation_key="totalrainin",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="24hrainin",
        translation_key="24hrainin",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="rrain_piezo",
        translation_key="rrain_piezo",
        native_unit_of_measurement=UnitOfVolumetricFlux.INCHES_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="erain_piezo",
        translation_key="erain_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="drain_piezo",
        translation_key="drain_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="wrain_piezo",
        translation_key="wrain_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="mrain_piezo",
        translation_key="mrain_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="yrain_piezo",
        translation_key="yrain_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="train_piezo",
        translation_key="train_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="24hrain_piezo",
        translation_key="24hrain_piezo",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.INCHES,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="co2in",
        translation_key="co2in",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="co2",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="co2in_24h",
        translation_key="co2in_24h",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="co2_24h",
        translation_key="co2_24h",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm25_co2",
        translation_key="pm25_co2",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm25_aqi_co2",
        translation_key="pm25_aqi_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm25_24h_co2",
        translation_key="pm25_24h_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm10_co2",
        translation_key="pm10_co2",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm10_aqi_co2",
        translation_key="pm10_aqi_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm10_24h_co2",
        translation_key="pm10_24h_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="lightning",
        translation_key="lightning",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="lightning_time",
        translation_key="lightning_time",
        icon="mdi:lightning-bolt",
    ),
    SensorEntityDescription(
        key="lightning_num",
        translation_key="lightning_num",
        icon="mdi:lightning-bolt",
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="con_batt",
        translation_key="con_batt",
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key="con_batt_volt",
        translation_key="con_batt_volt",
        icon="mdi:battery",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="con_ext_volt",
        translation_key="con_ext_volt",
        icon="mdi:battery",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="piezora_batt",
        translation_key="piezora_batt",
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key="srain_piezo",
        translation_key="srain_piezo",
        icon="mdi:weather-rainy",
    ),
    SensorEntityDescription(
        key="pm1_co2",
        translation_key="pm1_co2",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM1,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm1_aqi_co2",
        translation_key="pm1_aqi_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm1_24h_co2",
        translation_key="pm1_24h_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm4_co2",
        translation_key="pm4_co2",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm4_aqi_co2",
        translation_key="pm4_aqi_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="pm4_24h_co2",
        translation_key="pm4_24h_co2",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

ECOWITT_SENSORS_MAPPING: Final = {
    WittiotDataTypes.TEMPERATURE: SensorEntityDescription(
        key="TEMPERATURE",
        native_unit_of_measurement="°F",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WittiotDataTypes.HUMIDITY: SensorEntityDescription(
        key="HUMIDITY",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
    ),
    WittiotDataTypes.PM25: SensorEntityDescription(
        key="PM25",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WittiotDataTypes.AQI: SensorEntityDescription(
        key="AQI",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WittiotDataTypes.LEAK: SensorEntityDescription(
        key="LEAK",
        icon="mdi:water-alert",
    ),
    WittiotDataTypes.BATTERY: SensorEntityDescription(
        key="BATTERY",
        icon="mdi:battery",
    ),
    WittiotDataTypes.DISTANCE: SensorEntityDescription(
        key="DISTANCE",
        native_unit_of_measurement=UnitOfLength.FEET,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:arrow-expand-vertical",
    ),
    WittiotDataTypes.HEAT: SensorEntityDescription(
        key="HEAT",
        state_class=SensorStateClass.MEASUREMENT,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        MainDevEcowittSensor(coordinator, entry.unique_id, desc)
        for desc in SENSOR_DESCRIPTIONS
        if desc.key in coordinator.data
    )
    # Subdevice Data
    subsensors: list[SubDevEcowittSensor] = []
    for key in coordinator.data:
        if key in MultiSensorInfo.SENSOR_INFO:
            if MultiSensorInfo.SENSOR_INFO[key]["data_type"] == WittiotDataTypes.LEAK:
                continue
            mapping = ECOWITT_SENSORS_MAPPING[
                MultiSensorInfo.SENSOR_INFO[key]["data_type"]
            ]
            description = dataclasses.replace(
                mapping,
                key=key,
                name=MultiSensorInfo.SENSOR_INFO[key]["name"],
            )
            subsensors.append(
                SubDevEcowittSensor(
                    coordinator,
                    entry.unique_id,
                    MultiSensorInfo.SENSOR_INFO[key]["dev_type"],
                    description,
                )
            )
    async_add_entities(subsensors)


class MainDevEcowittSensor(
    CoordinatorEntity[EcowittDataUpdateCoordinator], SensorEntity
):
    """Define a Local sensor."""

    _attr_has_entity_name = True
    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: EcowittDataUpdateCoordinator,
        device_name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_name}")},
            manufacturer="Ecowitt",
            name=f"{device_name}",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
        )
        self._attr_unique_id = f"{device_name}_{description.key}"
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state."""
        return self.coordinator.data.get(self.entity_description.key)


class SubDevEcowittSensor(
    CoordinatorEntity[EcowittDataUpdateCoordinator], SensorEntity
):
    """Define an Local sensor."""

    _attr_has_entity_name = True
    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: EcowittDataUpdateCoordinator,
        device_name: str,
        sensor_type: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_name}_{sensor_type}")},
            manufacturer="Ecowitt",
            name=f"{device_name}_{sensor_type}",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
            via_device=(DOMAIN, f"{device_name}"),
        )
        self._attr_unique_id = f"{device_name}_{description.key}"
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state."""
        return self.coordinator.data.get(self.entity_description.key)
