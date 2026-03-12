"""Update entity for Ecowitt firmware."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up update entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EcowittFirmwareUpdateEntity(coordinator, entry.unique_id)])


class EcowittFirmwareUpdateEntity(CoordinatorEntity[EcowittDataUpdateCoordinator], UpdateEntity):
    """Represent Ecowitt gateway firmware updates."""

    _attr_has_entity_name = True
    _attr_name = "Firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE

    def __init__(self, coordinator: EcowittDataUpdateCoordinator, device_name: str) -> None:
        """Initialize update entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_name}_firmware"
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
            installed = firmware.get("installed_version")
            if isinstance(installed, str):
                return installed
        version = self.coordinator.data.get("ver")
        return str(version) if version is not None else None

    @property
    def latest_version(self) -> str | None:
        """Latest available firmware version."""
        firmware = self.coordinator.data.get("firmware_update", {})
        if not isinstance(firmware, dict):
            return None
        latest = firmware.get("latest_version")
        if isinstance(latest, str) and latest.strip():
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