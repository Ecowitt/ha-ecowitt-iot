"""Recovery settings must remain editable during an HTTP outage."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_ecowitt_iot.const import (
    CONF_AUTO_RESTART,
    CONF_MAC,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.1", CONF_MAC: "aa:bb:cc:dd:ee:ff"},
        unique_id="GW3000B-WIFIEEFF",
    )
    entry.add_to_hass(hass)
    return entry


async def test_enable_auto_recovery_offline_preserves_mac(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.ha_ecowitt_iot.config_flow.API") as api:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.0.2.1", CONF_UPDATE_INTERVAL: 10, CONF_AUTO_RESTART: True},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_AUTO_RESTART] is True
    assert entry.data[CONF_MAC] == "aa:bb:cc:dd:ee:ff"
    api.assert_not_called()


async def test_no_mac_cannot_enable_auto_restart(hass, entry):
    hass.config_entries.async_update_entry(entry, data={CONF_HOST: "192.0.2.1"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.0.2.1", CONF_UPDATE_INTERVAL: 10, CONF_AUTO_RESTART: True},
    )
    assert result["errors"] == {"base": "missing_mac"}
    assert not entry.data.get(CONF_AUTO_RESTART)


async def test_changing_host_still_requires_http_validation(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.ha_ecowitt_iot.config_flow.API") as api:
        api.return_value.request_loc_info = AsyncMock(side_effect=TimeoutError)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.0.2.2", CONF_UPDATE_INTERVAL: 10},
        )
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[CONF_HOST] == "192.0.2.1"


async def test_changing_host_rejects_wrong_gateway(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.ha_ecowitt_iot.config_flow.API") as api:
        api.return_value.request_loc_info = AsyncMock(
            return_value={"dev_name": "other"}
        )
        api.return_value.request_loc_allinfo = AsyncMock(
            return_value={"mac": "00:11:22:33:44:55"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.0.2.2", CONF_UPDATE_INTERVAL: 10},
        )
    assert result["errors"] == {"base": "device_mismatch"}
    assert entry.data[CONF_HOST] == "192.0.2.1"
