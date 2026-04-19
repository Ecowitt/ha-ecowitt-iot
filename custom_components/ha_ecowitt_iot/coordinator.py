"""The Ecowitt integration coordinator."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from aiohttp.client_exceptions import ClientError
from wittiot import API
from wittiot.errors import WittiotError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Transient errors tolerated via the cache-based retry path below.
_TRANSIENT_ERRORS = (WittiotError, ClientError, asyncio.TimeoutError)

# Per-request timeout. Generous so a busy single-threaded gateway has
# room to answer; prior code had no timeout and could hang 5 min on a
# half-dead socket (aiohttp default).
REQUEST_TIMEOUT_SECONDS = 60

# Number of consecutive failed polls tolerated before raising UpdateFailed.
# At update_interval=10s this bounds stale-data exposure to ~20s.
MAX_CONSECUTIVE_FAILURES = 3

# Firmware metadata rarely changes; refresh at most once per hour.
FIRMWARE_CHECK_INTERVAL_SECONDS = 3600


class EcowittDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Define an object to hold Ecowitt data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=10)
        )
        self.config_entry = config_entry
        self.api = API(
            self.config_entry.data[CONF_HOST], session=async_get_clientsession(hass)
        )
        self._consecutive_failures = 0
        self._last_good_data: dict[str, Any] = {}
        self._firmware_update_info: dict[str, Any] | None = None
        self._last_firmware_check: float = 0.0
        self._outage_logged = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                res: dict[str, Any] = await self.api.request_loc_allinfo()
        except _TRANSIENT_ERRORS as error:
            return self._handle_fetch_failure(error)

        res["firmware_update"] = await self._maybe_update_firmware_info()

        if self._outage_logged:
            _LOGGER.info(
                "Ecowitt gateway %s is reachable again",
                self.config_entry.data[CONF_HOST],
            )
            self._outage_logged = False
        self._consecutive_failures = 0
        self._last_good_data = res
        return res

    def _handle_fetch_failure(self, error: Exception) -> dict[str, Any]:
        self._consecutive_failures += 1
        if self._consecutive_failures < MAX_CONSECUTIVE_FAILURES and self._last_good_data:
            _LOGGER.debug(
                "Ecowitt fetch failed (%d/%d): %s; serving last known data",
                self._consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                error,
            )
            return self._last_good_data

        # Tolerance exhausted: drop the cache, log once, and mark unavailable.
        self._last_good_data = {}
        if not self._outage_logged:
            _LOGGER.warning(
                "Ecowitt gateway %s unreachable for %d consecutive polls (%s); "
                "entities will be unavailable until it recovers",
                self.config_entry.data[CONF_HOST],
                self._consecutive_failures,
                error,
            )
            self._outage_logged = True
        raise UpdateFailed(
            f"Gateway unreachable for {self._consecutive_failures} consecutive polls: {error}"
        ) from error

    async def _maybe_update_firmware_info(self) -> dict[str, Any]:
        # A firmware endpoint failure must not mask a successful data fetch.
        now = time.monotonic()
        if (
            self._firmware_update_info is not None
            and now - self._last_firmware_check < FIRMWARE_CHECK_INTERVAL_SECONDS
        ):
            return self._firmware_update_info

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                firmware_info: dict[str, Any] = await self.api.request_firmware_update_info()
        except _TRANSIENT_ERRORS as err:
            _LOGGER.debug(
                "Firmware info fetch failed; keeping previous metadata: %s", err
            )
            return self._firmware_update_info or {}

        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                check_info: dict[str, Any] = await self.api.request_firmware_update_check()
        except _TRANSIENT_ERRORS as err:
            firmware_info["check_supported"] = False
            firmware_info["install_supported"] = False
            firmware_info["error"] = str(err)
        else:
            response = check_info.get("response", {})
            if isinstance(response, dict):
                firmware_info["is_new"] = response.get(
                    "is_new", firmware_info.get("is_new", False)
                )
                firmware_info["release_summary"] = response.get(
                    "msg", firmware_info.get("release_summary")
                )
                firmware_info["check_response"] = response

        self._firmware_update_info = firmware_info
        self._last_firmware_check = now
        return firmware_info
