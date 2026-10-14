"""The Ecowitt Official Integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .coordinator import EcowittDataUpdateCoordinator
from .recovery import DATA_RECOVERY, async_get_recovery

_LOGGER = logging.getLogger(__name__)


PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
    Platform.BUTTON,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register recovery independently of successful config entry setup."""

    async def restart_gateway(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or entry.disabled_by is not None:
            raise ServiceValidationError(
                "Select an enabled Ecowitt integration instance"
            )
        await async_get_recovery(hass, entry).async_restart()

    async_register_admin_service(
        hass,
        DOMAIN,
        "restart_gateway",
        restart_gateway,
        schema=vol.Schema({vol.Required("config_entry_id"): str}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ecowitt Official Integration from a config entry."""

    coordinator = EcowittDataUpdateCoordinator(
        hass,
        entry,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 注册重新加载函数
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove persistent recovery data when an integration instance is deleted."""
    recovery = async_get_recovery(hass, entry)
    await recovery.async_remove()
    hass.data.get(DATA_RECOVERY, {}).pop(entry.entry_id, None)
