"""The Ecowitt integration coordinator."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
import asyncio

from aiohttp.client_exceptions import ClientConnectorError
from wittiot import API
from wittiot.errors import WittiotError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

SCAN_INTERVAL = timedelta(seconds=60)
MAX_CONSECUTIVE_FAILURES = 3

_LOGGER = logging.getLogger(__name__)


class EcowittDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Define an object to hold Ecowitt data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=10)
        )
        self.api = API(
            self.config_entry.data[CONF_HOST], session=async_get_clientsession(hass)
        )
        self._consecutive_failures = 0
        self._last_good_data: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, str | float | int]:
        """Update data."""
        res: dict[str, Any] = {}
        try:
            res = await self.api.request_loc_allinfo()
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
