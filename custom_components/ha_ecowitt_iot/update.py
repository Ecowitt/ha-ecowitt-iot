"""Update entity for Ecowitt firmware."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator


def _normalize_version(value: Any) -> str | None:
    """Extract a numeric firmware version from the device payload."""
    if value is None:
        return None
    match = re.search(r"([\d.]+)$", str(value).strip())
    if not match:
        return None
    return match.group(1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up update entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    registry = er.async_get(hass)
    canonical_uid = f"{entry.entry_id}_firmware"
    scoped_existing = [
        e
        for e in registry.entities.values()
        if e.platform == DOMAIN
        and e.domain == "update"
        and getattr(e, "config_entry_id", entry.entry_id) == entry.entry_id
    ]
    if scoped_existing:
        if not any(e.unique_id == canonical_uid for e in scoped_existing):
            registry.async_update_entity(scoped_existing[0].entity_id, new_unique_id=canonical_uid)
        for e in scoped_existing[1:]:
            if e.unique_id != canonical_uid:
                registry.async_remove(e.entity_id)
    async_add_entities([EcowittFirmwareUpdateEntity(coordinator, entry.unique_id)])


class EcowittFirmwareUpdateEntity(CoordinatorEntity[EcowittDataUpdateCoordinator], UpdateEntity):
    """Represent Ecowitt gateway firmware updates."""

    _attr_has_entity_name = True
    _attr_name = "Firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE

    def __init__(self, coordinator: EcowittDataUpdateCoordinator, device_name: str) -> None:
        """Initialize update entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_firmware"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_name}")},
            manufacturer="Ecowitt",
            name=f"{device_name}",
            model=coordinator.data.get("ver"),
            configuration_url=f"http://{coordinator.config_entry.data[CONF_HOST]}",
        )
        mac = coordinator.data.get("mac")
        if mac:
            self._attr_device_info["connections"] = {(dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        firmware = self.coordinator.data.get("firmware_update")
        return super().available and isinstance(firmware, dict) and firmware.get("check_supported", False)

    @property
    def installed_version(self) -> str | None:
        """Version currently installed on the device."""
        firmware = self.coordinator.data.get("firmware_update", {})
        if isinstance(firmware, dict):
            installed = _normalize_version(firmware.get("installed_version"))
            if installed:
                return installed
        return _normalize_version(self.coordinator.data.get("ver"))

    @property
    def latest_version(self) -> str | None:
        """Latest available firmware version."""
        firmware = self.coordinator.data.get("firmware_update", {})
        if not isinstance(firmware, dict):
            return None
        latest = _normalize_version(firmware.get("latest_version"))
        if latest:
            return latest
        return None

    @property
    def release_summary(self) -> str | None:
        """Summary of the latest release."""
        firmware = self.coordinator.data.get("firmware_update", {})
        if not isinstance(firmware, dict):
            return None
        summary = firmware.get("release_summary")
        if isinstance(summary, str) and summary.strip():
            return summary
        return None

    @property
    def supported_features(self) -> UpdateEntityFeature:
        """Return supported features for firmware update."""
        firmware = self.coordinator.data.get("firmware_update", {})
        if not isinstance(firmware, dict):
            return UpdateEntityFeature(0)
        if firmware.get("install_supported", False):
            return UpdateEntityFeature.INSTALL
        return UpdateEntityFeature(0)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra diagnostics for unsupported update paths."""
        firmware = self.coordinator.data.get("firmware_update")
        if not isinstance(firmware, dict):
            return {"check_supported": False, "reason": "firmware metadata unavailable"}
        attrs: dict[str, Any] = {"check_supported": firmware.get("check_supported", False), "install_supported": firmware.get("install_supported", False)}
        if firmware.get("is_new") is not None:
            attrs["is_new"] = firmware.get("is_new")
        if firmware.get("install_endpoint"):
            attrs["install_endpoint"] = firmware.get("install_endpoint")
        return attrs

    async def async_install(self, version: str | None, backup: bool) -> None:
        """Install latest firmware update."""
        del version, backup
        await self.coordinator.api.install_firmware_update()
        self._attr_in_progress = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
        self._attr_in_progress = False
        self.async_write_ha_state()
