"""Config flow for Ecowitt Official Integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from aiohttp.client_exceptions import ClientError
from wittiot import API
from wittiot.errors import WittiotError

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import CONF_MAC, CONF_UPDATE_INTERVAL, CONF_UPDATE_LAST_SEEN, DOMAIN, DEFAULT_UPDATE_INTERVAL, DEFAULT_UPDATE_LAST_SEEN

_LOGGER = logging.getLogger(__name__)

_CONNECT_ERRORS = (WittiotError, ClientError, asyncio.TimeoutError)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ecowitt Official Integration."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the local step."""
        errors = {}

        if user_input is not None:
            api = API(
                user_input[CONF_HOST],
                session=aiohttp_client.async_get_clientsession(self.hass),
            )

            devices: dict[str, Any] | None = None
            try:
                devices = await api.request_loc_info()
            except _CONNECT_ERRORS:
                errors["base"] = "cannot_connect"
            else:
                _LOGGER.debug("New data received: %s", devices)
                if not devices:
                    errors["base"] = "no_devices"

            if not errors and devices:
                unique_id = devices["dev_name"]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                try:
                    all_info = await api.request_loc_allinfo()
                    mac = all_info.get("mac", "")
                except _CONNECT_ERRORS:
                    mac = ""

                entry_data = {**user_input, CONF_MAC: mac}
                return self.async_create_entry(title=unique_id, data=entry_data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(int, vol.Range(min=5)),
                    vol.Required(
                        CONF_UPDATE_LAST_SEEN, default=DEFAULT_UPDATE_LAST_SEEN
                    ): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ecowitt integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            api = API(
                user_input[CONF_HOST],
                session=aiohttp_client.async_get_clientsession(self.hass),
            )

            try:
                devices = await api.request_loc_info()
            except _CONNECT_ERRORS:
                errors["base"] = "cannot_connect"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    try:
                        all_info = await api.request_loc_allinfo()
                        new_mac = all_info.get("mac", "")
                    except _CONNECT_ERRORS:
                        new_mac = ""

                    expected_mac = self.config_entry.data.get(CONF_MAC, "")
                    if expected_mac and new_mac and new_mac != expected_mac:
                        _LOGGER.warning(
                            "Refusing to update IP %s: device mismatch. "
                            "Expected MAC %s, got %s. "
                            "Please create a new integration for this device.",
                            user_input[CONF_HOST],
                            expected_mac,
                            new_mac,
                        )
                        errors["base"] = "device_mismatch"
                    else:
                        if not expected_mac and new_mac:
                            _LOGGER.info(
                                "Updating config with MAC %s for device at %s",
                                new_mac,
                                user_input[CONF_HOST],
                            )

                        new_data = {
                            **self.config_entry.data,
                            **user_input,
                            CONF_MAC: new_mac,
                        }
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, data=new_data
                        )

                        return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=self.config_entry.data.get(CONF_HOST)
                    ): str,
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.data.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(int, vol.Range(min=5)),
                    vol.Required(
                        CONF_UPDATE_LAST_SEEN,
                        default=self.config_entry.data.get(
                            CONF_UPDATE_LAST_SEEN, DEFAULT_UPDATE_LAST_SEEN
                        ),
                    ): bool,
                }
            ),
            errors=errors,
        )