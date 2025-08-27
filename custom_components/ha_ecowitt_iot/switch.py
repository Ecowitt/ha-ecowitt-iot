import logging
import time
from wittiot import API
import asyncio
import dataclasses
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.event import async_call_later
from homeassistant.const import (
    CONF_HOST,
)
from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_DESCRIPTIONS = (
    SwitchEntityDescription(
        key="iot_running",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """设置开关平台."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # 为每个设备创建开关实体
    switches = []
    if "iot_list" in coordinator.data:
        iot_data = coordinator.data["iot_list"]
        commands = iot_data["command"]
        desc_map = {desc.key: desc for desc in SWITCH_DESCRIPTIONS}
        for i, item in enumerate(commands):
            rfnet_state = item.get("rfnet_state")
            if rfnet_state == 0:
                continue
            for key in list(item):
                if key in desc_map:
                    desc = desc_map[key]
                    device_desc = dataclasses.replace(
                        desc,
                        key=f"{item.get('nickname')}_{desc.key}",
                    )
                    switches.append(
                        EcowittSwitch(
                            coordinator=coordinator,
                            device_id=item.get("nickname"),
                            description=device_desc,
                            unique_id=entry.unique_id,
                        )
                    )
    async_add_entities(switches)
    return True


class EcowittSwitch(CoordinatorEntity, SwitchEntity):
    """表示Ecowitt设备的开关实体."""

    def __init__(
        self,
        coordinator: EcowittDataUpdateCoordinator,
        device_id: str,
        description: SwitchEntityDescription,
        unique_id: str,
    ) -> None:
        """表示Ecowitt设备的开关实体."""
        super().__init__(coordinator)
        self.device_id = device_id
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

        self._pending_state = None  # 跟踪待确认的状态
        self._pending_timestamp = None  # 记录状态改变的时间
        self._timeout_handle = None  # 超时处理句柄
        # 设置设备信息
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_id}")},
            name=f"{device_id}",
            manufacturer="Ecowitt",
            model=coordinator.data["ver"],
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
            via_device=(DOMAIN, unique_id),
        )

        if "iot_list" in self.coordinator.data:
            iot_data = self.coordinator.data["iot_list"]
            commands = iot_data["command"]
            for i, item in enumerate(commands):
                nickname = item.get("nickname")
                rfnet_state = item.get("rfnet_state")
                if rfnet_state == 0:
                    continue
                if nickname == self.device_id:
                    # key = self.entity_description.key.split("_", 1)[1]
                    self._iot_id = item.get("id")
                    self._iot_model = item.get("model")
                    # self._iot_is_on = item.get("iot_running")

    @property
    def is_on(self) -> bool:
        """从协调器获取设备数据."""
        return self._get_actual_state()  # 如果数据不可用返回None

    async def async_turn_on(self, **kwargs):
        """打开设备."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs):
        """关闭设备."""
        await self._async_set_state(False)

    def _get_actual_state(self) -> bool:
        """从协调器获取实际设备状态."""
        if "iot_list" in self.coordinator.data:
            iot_data = self.coordinator.data["iot_list"]
            commands = iot_data["command"]
            for i, item in enumerate(commands):
                nickname = item.get("nickname")
                rfnet_state = item.get("rfnet_state")
                if rfnet_state == 0:
                    continue
                if nickname == self.device_id:
                    # key = self.entity_description.key.split("_", 1)[1]
                    return bool(item.get("iot_running", 0))
        return False  # 默认返回关状态

    async def _async_set_state(self, state: bool):
        """设置设备状态（带待处理状态管理）"""
        # 取消之前的超时检查
        if self._timeout_handle:
            self._timeout_handle()
            self._timeout_handle = None

        # 设置待处理状态
        self._pending_state = state
        self._pending_timestamp = time.time()

        # 乐观更新：立即改变UI状态
        self._attr_is_on = state
        self.async_write_ha_state()

        # 发送控制命令
        state_value = 1 if state else 0
        await self.coordinator.api.switch_iotdevice(
            self._iot_id, self._iot_model, state_value
        )

        # 设置状态验证超时（5秒后检查实际状态）
        self._timeout_handle = async_call_later(
            self.hass,
            5,  # 7秒后验证状态
            self._async_verify_state,
        )

        # 延迟1秒后请求协调器更新数据
        await self.coordinator.async_request_refresh()

    async def _async_verify_state(self, _):
        """验证设备实际状态是否与预期一致"""
        self._timeout_handle = None

        # 获取当前实际状态
        current_state = self._get_actual_state()

        if self._pending_state == current_state:
            # 状态匹配，清除待处理标志
            self._pending_state = None
            self._pending_timestamp = None
        else:
            # 状态不匹配，恢复实际状态
            self._attr_is_on = current_state
            self._pending_state = None
            self._pending_timestamp = None
            self.async_write_ha_state()
            # _LOGGER.warning(
            #     "设备状态未按预期改变。预期: %s, 实际: %s",
            #     "开" if self._pending_state else "关",
            #     "开" if current_state else "关",
            # )
