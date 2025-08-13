"""The Ecowitt integration coordinator."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

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
        self._cached_data: dict = {}  # 添加缓存
        self._last_successful_update = None

    async def _async_update_data(self) -> dict[str, str | float | int]:
        """Update data."""
        res = {}
        try:
            res = await self.api.request_loc_allinfo()
            self._cached_data = res  # 缓存数据
            self._last_successful_update = datetime.now()
        except (WittiotError, ClientConnectorError) as error:
            # 检查缓存是否过期（例如超过30分钟）
            if (self._last_successful_update and 
                (datetime.now() - self._last_successful_update).total_seconds() > 1800):
                raise UpdateFailed(error) from error
            # 使用缓存数据，但标记为"过时"
            self._cached_data.setdefault("_stale", True)
            return self._cached_data
           # raise UpdateFailed(error) from error
        # _LOGGER.info("Get device data: %s", res)
        return res
