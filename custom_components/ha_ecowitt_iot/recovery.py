"""Gateway recovery independent of the HTTP polling coordinator."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import CONF_AUTO_RESTART, CONF_MAC, DOMAIN
from .tcp import CMD_READ_MAC, CMD_REBOOT, GatewayCommandError, async_command

_LOGGER = logging.getLogger(__name__)
DATA_RECOVERY = f"{DOMAIN}_recovery"
RESTART_FAILURE_THRESHOLD = 3
RESTART_COOLDOWN = 1800
RESTART_REFRESH_DELAY = 10


class GatewayRecovery:
    """Share failure counts and persistent cooldown across setup retries/reloads."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.failures = 0
        self._last_restart = 0.0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.recovery"
        )

    def reset_failures(self) -> None:
        """Only a successful, identity-verified HTTP poll resets failures."""
        self.failures = 0

    async def async_remove(self) -> None:
        """Delete the cooldown when the integration entry is removed."""
        await self._store.async_remove()

    async def async_poll_failed(self) -> None:
        """Try opt-in recovery after repeated HTTP failures, including setup."""
        self.failures = min(self.failures + 1, RESTART_FAILURE_THRESHOLD)
        if (
            not self.entry.data.get(CONF_AUTO_RESTART, False)
            or self.failures < RESTART_FAILURE_THRESHOLD
        ):
            return
        try:
            await self.async_restart()
        except HomeAssistantError as error:
            _LOGGER.debug("Automatic gateway recovery skipped/failed: %s", error)

    async def async_restart(self) -> None:
        """Verify full MAC over TCP, save cooldown, then request a restart."""
        async with self._lock:
            if not self._loaded:
                try:
                    state = await self._store.async_load()
                except OSError as error:
                    raise HomeAssistantError(
                        "Cannot load gateway recovery state"
                    ) from error
                if state is not None:
                    if not isinstance(state, dict):
                        raise HomeAssistantError("Invalid gateway recovery state")
                    value = state.get("last_restart")
                    if (
                        not isinstance(value, (float, int))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise HomeAssistantError("Invalid gateway recovery state")
                    self._last_restart = value
                self._loaded = True
            remaining = self._last_restart + RESTART_COOLDOWN - time.time()
            if remaining > 0:
                raise HomeAssistantError(
                    f"Gateway restart cooldown active for another {int(remaining) + 1} seconds"
                )
            expected = self.entry.data.get(CONF_MAC, "")
            if not isinstance(expected, str):
                expected = ""
            normalized = expected.replace(":", "").replace("-", "")
            if not re.fullmatch(r"[0-9a-fA-F]{12}", normalized):
                raise HomeAssistantError(
                    "A full MAC address must be recorded by a successful HTTP connection "
                    "before the gateway can be restarted"
                )
            host = self.entry.data[CONF_HOST]
            try:
                actual = await async_command(host, CMD_READ_MAC)
            except GatewayCommandError as error:
                raise HomeAssistantError(str(error)) from error
            if actual != bytes.fromhex(normalized):
                raise HomeAssistantError(
                    "TCP gateway MAC does not match this integration; restart refused"
                )

            # Persist before sending: a lost reply or HA restart must not cause a loop.
            self._last_restart = time.time()
            try:
                await self._store.async_save({"last_restart": self._last_restart})
            except OSError as error:
                raise HomeAssistantError(
                    "Cannot save gateway recovery cooldown"
                ) from error
            self.failures = 0
            _LOGGER.warning("Requesting TCP restart of Ecowitt gateway %s", host)
            try:
                result = await async_command(host, CMD_REBOOT)
            except GatewayCommandError as error:
                self._schedule_refresh()
                raise HomeAssistantError(
                    "Restart acknowledgement unavailable; the gateway may have restarted. "
                    "Cooldown remains active"
                ) from error
            if result != b"\x00":
                raise HomeAssistantError(
                    "Gateway rejected restart; cooldown remains active"
                )
            self._schedule_refresh()
            _LOGGER.info("Ecowitt gateway %s accepted the restart request", host)

    def _schedule_refresh(self) -> None:
        """Retry HTTP after boot, even when initial setup could not finish."""

        async def refresh(_now: Any) -> None:
            entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
            if entry is None or entry.disabled_by is not None:
                return
            coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if coordinator is not None:
                await coordinator.async_request_refresh()
            else:
                await self.hass.config_entries.async_reload(entry.entry_id)

        async_call_later(self.hass, RESTART_REFRESH_DELAY, refresh)


def async_get_recovery(hass: HomeAssistant, entry: ConfigEntry) -> GatewayRecovery:
    """Return the same manager during failed setup attempts and reloads."""
    managers = hass.data.setdefault(DATA_RECOVERY, {})
    if entry.entry_id not in managers:
        managers[entry.entry_id] = GatewayRecovery(hass, entry)
    return managers[entry.entry_id]
