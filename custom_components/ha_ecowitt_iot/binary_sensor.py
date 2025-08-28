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
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator

BINARYSENSOR_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="srain_piezo",
        translation_key="srain_piezo",
        icon="mdi:weather-rainy",
        device_class=BinarySensorDeviceClass.MOISTURE,  # 设备类别为湿度/漏水
    ),
)


LEAK_DETECTION_SENSOR: Final = {
    WittiotDataTypes.LEAK: BinarySensorEntityDescription(
        key="LEAK",
        icon="mdi:water-alert",
        device_class=BinarySensorDeviceClass.MOISTURE,  # 设备类别为湿度/漏水
    ),
    WittiotDataTypes.BATTERY_BINARY: BinarySensorEntityDescription(
        key="BATTERY_BINARY",
        icon="mdi:battery",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}

IOT_BINARYSENSOR_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="rfnet_state",
        translation_key="rfnet_state",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="iot_running",
        translation_key="iot_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


# 在设备设置函数中创建实体
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """设置二进制传感器平台."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # 添加普通传感器
    async_add_entities(
        MainDevEcowittBinarySensor(coordinator, entry.unique_id, desc)
        for desc in BINARYSENSOR_DESCRIPTIONS
        if desc.key in coordinator.data
    )

    # Subdevice Data
    binary_sensors: list[SubDevEcowittBinarySensor] = []
    for key in coordinator.data:
        if key in MultiSensorInfo.SENSOR_INFO and MultiSensorInfo.SENSOR_INFO[key][
            "data_type"
        ] in (WittiotDataTypes.LEAK, WittiotDataTypes.BATTERY_BINARY):
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

    if "iot_list" in coordinator.data:
        iot_sensors: list[IotDeviceBinarySensor] = []
        desc_map = {desc.key: desc for desc in IOT_BINARYSENSOR_DESCRIPTIONS}
        iot_data = coordinator.data["iot_list"]
        commands = iot_data["command"]
        for i, item in enumerate(commands):
            nickname = item.get("nickname")
            if nickname is None:
                continue
            for key in list(item):
                if key in desc_map:
                    desc = desc_map[key]
                    device_desc = dataclasses.replace(
                        desc,
                        key=f"{nickname}_{desc.key}",
                        # name=f"{device_info.get('name', f'设备 {device_id}')} {desc.name}",
                    )
                    # 添加到实体列表
                    iot_sensors.append(
                        IotDeviceBinarySensor(
                            coordinator=coordinator,
                            device_id=nickname,
                            description=device_desc,
                            unique_id=entry.unique_id,
                        )
                    )
        async_add_entities(iot_sensors)


class MainDevEcowittBinarySensor(
    CoordinatorEntity[EcowittDataUpdateCoordinator],  # 继承 CoordinatorEntity
    BinarySensorEntity,  # 继承 BinarySensorEntity
):
    """Ecowitt 漏水检测二进制传感器."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EcowittDataUpdateCoordinator,
        device_name: str,
        description: BinarySensorEntityDescription,
    ) -> None:
        """初始化漏水检测传感器."""
        super().__init__(coordinator)

        # 设置设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_name}")},
            manufacturer="Ecowitt",
            name=f"{device_name}",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
        )

        # 设置唯一ID和实体描述
        self._attr_unique_id = f"{device_name}_{description.key}"
        self.entity_description = description
        self._sensor_key = description.key  # 存储用于数据访问的键

    @property
    def is_on(self) -> bool | None:
        """返回二进制传感器状态 (True 表示检测到漏水)."""
        # 从协调器获取当前数据
        value = self.coordinator.data.get(self.entity_description.key)
        if value is not None:
            return value != "No rain"
        return None  # 如果数据不可用返回None

    @property
    def available(self) -> bool:
        """实体是否可用"""
        return super().available and self._sensor_key in self.coordinator.data


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_name}")},
            manufacturer="Ecowitt",
            name=f"{device_name}",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
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


class IotDeviceBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """表示 IoT 设备的传感器实体"""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EcowittDataUpdateCoordinator,
        device_id: str,
        description: BinarySensorEntityDescription,
        unique_id: str,
    ) -> None:
        """初始化 IoT 设备传感器"""
        super().__init__(coordinator)
        self.device_id = device_id
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

        # 设置设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_id}")},
            name=f"{device_id}",
            manufacturer="Ecowitt",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
            via_device=(DOMAIN, unique_id),
        )

    @property
    def is_on(self) -> bool | None:
        """返回二进制传感器状态 (True 表示检测到漏水)."""
        """获取传感器值"""
        # # 从协调器获取设备数据
        if "iot_list" in self.coordinator.data:
            iot_data = self.coordinator.data["iot_list"]
            commands = iot_data["command"]
            for i, item in enumerate(commands):
                nickname = item.get("nickname")
                if nickname is None:
                    continue
                if nickname == self.device_id:
                    key = self.entity_description.key.split("_", 1)[1]
                    return item.get(key, None)
        return None  # 如果数据不可用返回None
