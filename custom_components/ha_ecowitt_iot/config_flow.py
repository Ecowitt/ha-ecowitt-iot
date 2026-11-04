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

from .const import (
    CONF_AUTO_RESTART,
    CONF_FIRMWARE_CHECK,
    CONF_MAC,
    CONF_UPDATE_INTERVAL,
    DEFAULT_FIRMWARE_CHECK,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .recovery import is_full_mac, normalize_mac

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
            data_schema=vol.Schema( {
                vol.Required(CONF_HOST): str,
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(int, vol.Range(min=5)),
            }),
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
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_HOST] == self.config_entry.data[CONF_HOST]:
                # Recovery must be configurable while the HTTP service is down.
                # An unchanged address does not require learning a new identity.
                if user_input.get(
                    CONF_AUTO_RESTART, False
                ) and not is_full_mac(self.config_entry.data.get(CONF_MAC)):
                    errors["base"] = "missing_mac"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={**self.config_entry.data, **user_input},
                    )
                    return self.async_create_entry(title="", data={})
            else:
                return await self._async_update_host(user_input)

        return self._show_form(errors)

    def _show_form(self, errors: dict[str, str]) -> FlowResult:
        """Show the options form, pre-filled with the current values."""
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
                    vol.Optional(
                        CONF_FIRMWARE_CHECK,
                        default=self.config_entry.data.get(
                            CONF_FIRMWARE_CHECK, DEFAULT_FIRMWARE_CHECK
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_AUTO_RESTART,
                        default=self.config_entry.data.get(CONF_AUTO_RESTART, False),
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def _async_update_host(self, user_input: dict[str, Any]) -> FlowResult:
        """Require HTTP identity validation before accepting a new gateway address."""
        errors: dict[str, str] = {}
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

        new_mac = ""
        if not errors:
            try:
                all_info = await api.request_loc_allinfo()
                new_mac = all_info.get("mac", "")
            except _CONNECT_ERRORS:
                errors["base"] = "cannot_connect"

        # A new address must prove its identity: never persist a new host without
        # a complete MAC address read from that host.
        if not errors and not is_full_mac(new_mac):
            errors["base"] = "cannot_connect"

        if not errors:
            expected_mac = self.config_entry.data.get(CONF_MAC, "")
            if is_full_mac(expected_mac) and normalize_mac(new_mac) != normalize_mac(
                expected_mac
            ):
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
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, **user_input, CONF_MAC: new_mac},
                )
                return self.async_create_entry(title="", data={})

        return self._show_form(errors)
