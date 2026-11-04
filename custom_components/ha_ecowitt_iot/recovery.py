"""Gateway recovery independent of the HTTP polling coordinator."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from typing import Any, Callable

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
RESTART_FAILURE_THRESHOLD = 6
# A gateway must be unreachable for this long before an automatic restart, so a
# brief network blip (router/Wi-Fi restart) does not power-cycle the gateway.
RESTART_MIN_OUTAGE_SECONDS = 600
RESTART_COOLDOWN = 1800
RESTART_REFRESH_DELAY = 10
# Hard stop against reboot loops: at most this many automatic restarts are
# allowed without an intervening successful poll. After that, automatic
# recovery pauses until a poll succeeds or the user restarts manually.
MAX_AUTO_RESTARTS_WITHOUT_SUCCESS = 1


def normalize_mac(value: Any) -> str:
    """Return a MAC address without separators or a 0x prefix."""
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"[\s:\-]", "", value)
    return normalized.removeprefix("0x").removeprefix("0X")


def is_full_mac(value: Any) -> bool:
    """Return True if the value is a complete 12-digit hexadecimal MAC address."""
    return bool(re.fullmatch(r"[0-9a-fA-F]{12}", normalize_mac(value)))


class GatewayRecovery:
    """Share failure counts and persistent cooldown across setup retries/reloads."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.failures = 0
        self._first_failure_ts: float | None = None
        self._auto_restarts = 0
        self._loop_guard_logged = False
        self._paused_notification_id = f"ecowitt_auto_restart_paused_{entry.entry_id}"
        self._last_restart = 0.0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._cancel_refresh: Callable[[], None] | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.recovery"
        )

    def _clear_failure_window(self) -> None:
        """Clear the failure count for the current outage."""
        self.failures = 0
        self._first_failure_ts = None

    def reset_failures(self) -> None:
        """Only a successful, identity-verified HTTP poll resets failures."""
        self._clear_failure_window()
        self._auto_restarts = 0
        if self._loop_guard_logged:
            self._loop_guard_logged = False
            self.hass.async_create_task(self._async_dismiss_paused_notification())

    async def async_remove(self) -> None:
        """Delete the cooldown when the integration entry is removed."""
        self._cancel_scheduled_refresh()
        await self._store.async_remove()

    async def async_poll_failed(self) -> None:
        """Count a failed poll; recover only after a sustained, opted-in outage."""
        self.failures = min(self.failures + 1, RESTART_FAILURE_THRESHOLD)
        if self._first_failure_ts is None:
            self._first_failure_ts = time.monotonic()
        if (
            not self.entry.data.get(CONF_AUTO_RESTART, False)
            or self.failures < RESTART_FAILURE_THRESHOLD
            or time.monotonic() - self._first_failure_ts < RESTART_MIN_OUTAGE_SECONDS
        ):
            return
        if self._auto_restarts >= MAX_AUTO_RESTARTS_WITHOUT_SUCCESS:
            await self._async_pause_after_loop_guard()
            return
        try:
            await self.async_restart(automatic=True)
        except HomeAssistantError as error:
            _LOGGER.debug("Automatic gateway recovery skipped/failed: %s", error)

    async def _async_pause_after_loop_guard(self) -> None:
        """Stop automatic restarts after repeated unsuccessful attempts."""
        if self._loop_guard_logged:
            return
        self._loop_guard_logged = True
        host = self.entry.data.get(CONF_HOST, "")
        _LOGGER.warning(
            "Automatic gateway recovery paused for %s after %d unsuccessful "
            "restart(s) without a successful poll; manual intervention required",
            host,
            self._auto_restarts,
        )
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                service_data={
                    "title": "Ecowitt – Automatic gateway restart paused",
                    "message": (
                        f"The gateway at `{host}` did not recover after "
                        f"{self._auto_restarts} automatic restart(s). Automatic "
                        "restart is paused until a poll succeeds; check the "
                        "gateway manually."
                    ),
                    "notification_id": self._paused_notification_id,
                },
                blocking=False,
            )
        except HomeAssistantError as error:  # best effort only
            _LOGGER.debug("Could not create restart-paused notification: %s", error)

    async def _async_dismiss_paused_notification(self) -> None:
        """Dismiss the paused-restart notification after a successful poll."""
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                service_data={"notification_id": self._paused_notification_id},
                blocking=False,
            )
        except HomeAssistantError as error:  # best effort only
            _LOGGER.debug("Could not dismiss restart-paused notification: %s", error)

    async def async_restart(self, *, automatic: bool = False) -> None:
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
            normalized = normalize_mac(expected)
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

            if automatic:
                self._auto_restarts += 1

            # Persist before sending: a lost reply or HA restart must not cause a loop.
            self._last_restart = time.time()
            try:
                await self._store.async_save({"last_restart": self._last_restart})
            except OSError as error:
                raise HomeAssistantError(
                    "Cannot save gateway recovery cooldown"
                ) from error
            self._clear_failure_window()
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

    def _cancel_scheduled_refresh(self) -> None:
        """Cancel a previously scheduled post-boot refresh, if any."""
        if self._cancel_refresh is not None:
            self._cancel_refresh()
            self._cancel_refresh = None

    def _schedule_refresh(self) -> None:
        """Retry HTTP after boot, even when initial setup could not finish."""
        self._cancel_scheduled_refresh()

        async def refresh(_now: Any) -> None:
            self._cancel_refresh = None
            entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
            if entry is None or entry.disabled_by is not None:
                return
            coordinator = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if coordinator is not None:
                await coordinator.async_request_refresh()
            else:
                await self.hass.config_entries.async_reload(entry.entry_id)

        self._cancel_refresh = async_call_later(
            self.hass, RESTART_REFRESH_DELAY, refresh
        )


def async_get_recovery(hass: HomeAssistant, entry: ConfigEntry) -> GatewayRecovery:
    """Return the same manager during failed setup attempts and reloads."""
    managers = hass.data.setdefault(DATA_RECOVERY, {})
    if entry.entry_id not in managers:
        managers[entry.entry_id] = GatewayRecovery(hass, entry)
    return managers[entry.entry_id]
