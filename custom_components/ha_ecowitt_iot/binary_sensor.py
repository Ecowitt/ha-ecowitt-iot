from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
)
import dataclasses
from typing import Final
from wittiot import MultiSensorInfo, WittiotDataTypes
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator


LEAK_DETECTION_SENSOR: Final = {
    WittiotDataTypes.LEAK: BinarySensorEntityDescription(
        key="LEAK",
        icon="mdi:water-alert",
        device_class=BinarySensorDeviceClass.MOISTURE,  # 设备类别为湿度/漏水
    ),
}


# 在设备设置函数中创建实体
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """设置二进制传感器平台."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Subdevice Data
    binary_sensors: list[SubDevEcowittBinarySensor] = []
    for key in coordinator.data:
        if (
            key in MultiSensorInfo.SENSOR_INFO
            and MultiSensorInfo.SENSOR_INFO[key]["data_type"] == WittiotDataTypes.LEAK
        ):
            mapping = LEAK_DETECTION_SENSOR[
                MultiSensorInfo.SENSOR_INFO[key]["data_type"]
            ]
            description = dataclasses.replace(
                mapping,
                key=key,
                name=MultiSensorInfo.SENSOR_INFO[key]["name"],
            )
            binary_sensors.append(
                SubDevEcowittBinarySensor(
                    coordinator,
                    entry.unique_id,
                    MultiSensorInfo.SENSOR_INFO[key]["dev_type"],
                    description,
                )
            )
    async_add_entities(binary_sensors)


class SubDevEcowittBinarySensor(
    CoordinatorEntity[EcowittDataUpdateCoordinator],  # 继承 CoordinatorEntity
    BinarySensorEntity,  # 继承 BinarySensorEntity
):
    """Ecowitt 漏水检测二进制传感器."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EcowittDataUpdateCoordinator,
        device_name: str,
        sensor_type: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """初始化漏水检测传感器."""
        super().__init__(coordinator)

        # 设置设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_name}_{sensor_type}")},
            manufacturer="Ecowitt",
            name=f"{device_name}_{sensor_type}",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
            via_device=(DOMAIN, f"{device_name}"),
        )

        # 设置唯一ID和实体描述
        self._attr_unique_id = f"{device_name}_{description.key}"
        self.entity_description = description
        self._sensor_key = description.key  # 存储用于数据访问的键

    @property
    def is_on(self) -> bool | None:
        """返回二进制传感器状态 (True 表示检测到漏水)."""
        # 从协调器获取当前数据
        leak_value = self.coordinator.data.get(self.entity_description.key)
        if leak_value is not None:
            return leak_value != "Normal"  # 1=漏水(True)，0=正常(False)
        return None  # 如果数据不可用返回None

    @property
    def available(self) -> bool:
        """实体是否可用"""
        return super().available and self._sensor_key in self.coordinator.data
