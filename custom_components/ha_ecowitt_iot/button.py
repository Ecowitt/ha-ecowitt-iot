"""Restart buttons that remain usable during an HTTP polling outage."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MAC, DOMAIN
from .coordinator import EcowittDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add a restart control for a gateway with a recorded identity."""
    if entry.data.get(CONF_MAC):
        async_add_entities([EcowittRestartButton(hass.data[DOMAIN][entry.entry_id])])


class EcowittRestartButton(
    CoordinatorEntity[EcowittDataUpdateCoordinator], ButtonEntity
):
    """Request a MAC-verified TCP restart independently of HTTP availability."""

    _attr_has_entity_name = True
    _attr_translation_key = "restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EcowittDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_restart"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.unique_id)})

    @property
    def available(self) -> bool:
        """The TCP recovery path must remain callable when HTTP fails."""
        return bool(self.coordinator.config_entry.data.get(CONF_MAC))

    async def async_press(self) -> None:
        """Restart the gateway, never Home Assistant itself."""
        await self.coordinator.recovery.async_restart()
