"""The Ecowitt integration coordinator."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
import asyncio
import time
from aiohttp.client_exceptions import ClientConnectorError
from wittiot import API
from wittiot.errors import WittiotError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

MAX_CONSECUTIVE_FAILURES = 3
FIRMWARE_CHECK_INTERVAL_SECONDS = 3600

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict[str, str | float | int]:
        res: dict[str, Any] = {}
        try:
            res = await self.api.request_loc_allinfo()

            now = time.monotonic()
            if (
                self._firmware_update_info is None
                or now - self._last_firmware_check >= FIRMWARE_CHECK_INTERVAL_SECONDS
            ):
                firmware_info: dict[str, Any] = await self.api.request_firmware_update_info()
                try:
                    check_info: dict[str, Any] = await self.api.request_firmware_update_check()
                except WittiotError as err:
                    firmware_info["check_supported"] = False
                    firmware_info["install_supported"] = False
                    firmware_info["error"] = str(err)
                else:
                    response = check_info.get("response", {})
                    if isinstance(response, dict):
                        firmware_info["is_new"] = response.get("is_new", firmware_info.get("is_new", False))
                        firmware_info["release_summary"] = response.get("msg", firmware_info.get("release_summary"))
                        firmware_info["check_response"] = response
                self._firmware_update_info = firmware_info
                self._last_firmware_check = now
            res["firmware_update"] = self._firmware_update_info or {}

        except (WittiotError, ClientConnectorError, asyncio.TimeoutError) as error:
            self._consecutive_failures += 1
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self._last_good_data = {}
                raise UpdateFailed(error) from error
            if self._last_good_data:
                return self._last_good_data
            raise UpdateFailed(error) from error

        self._consecutive_failures = 0
        self._last_good_data = res
        return res
