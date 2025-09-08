"""Config flow for Ecowitt Official Integration."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol
from wittiot import API
from wittiot.errors import WittiotError

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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

            try:
                devices = await api.request_loc_info()
            except WittiotError:
                errors["base"] = "cannot_connect"
            _LOGGER.debug("New data received: %s", devices)

            if not devices:
                errors["base"] = "no_devices"

            if not errors:
                unique_id = devices["dev_name"]
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=unique_id, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ecowitt integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            # 验证新的设置
            api = API(
                user_input[CONF_HOST],
                session=aiohttp_client.async_get_clientsession(self.hass),
            )

            try:
                devices = await api.request_loc_info()
            except WittiotError:
                errors["base"] = "cannot_connect"
            else:
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    # 更新配置条目
                    new_data = {**self.config_entry.data, **user_input}
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=new_data
                    )

                    # 如果需要，也可以更新唯一ID和标题
                    unique_id = devices["dev_name"]
                    if unique_id != self.config_entry.unique_id:
                        self.hass.config_entries.async_update_entry(
                            self.config_entry, unique_id=unique_id, title=unique_id
                        )

                    return self.async_create_entry(title="", data={})

        # 显示表单，预填当前值
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=self.config_entry.data.get(CONF_HOST)
                    ): str
                }
            ),
            errors=errors,
        )
