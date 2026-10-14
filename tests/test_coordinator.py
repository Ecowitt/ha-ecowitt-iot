"""HTTP polling failures drive recovery, including failed initial setup."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_ecowitt_iot import async_setup
from custom_components.ha_ecowitt_iot.const import CONF_AUTO_RESTART, CONF_MAC, DOMAIN
from custom_components.ha_ecowitt_iot.coordinator import EcowittDataUpdateCoordinator
from custom_components.ha_ecowitt_iot.tcp import CMD_READ_MAC, CMD_REBOOT


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GW3000B-WIFIEEFF",
        data={
            CONF_HOST: "192.0.2.1",
            CONF_MAC: "aa:bb:cc:dd:ee:ff",
            CONF_AUTO_RESTART: True,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_poll_failures_trigger_auto_reboot_and_success_resets(hass, entry):
    with (
        patch("custom_components.ha_ecowitt_iot.coordinator.API") as api,
        patch(
            "custom_components.ha_ecowitt_iot.recovery.async_command",
            new_callable=AsyncMock,
        ) as command,
        patch("custom_components.ha_ecowitt_iot.recovery.async_call_later"),
    ):
        api.return_value.request_loc_allinfo = AsyncMock(side_effect=TimeoutError)
        command.side_effect = [bytes.fromhex("aabbccddeeff"), b"\x00"]
        # A new coordinator is made on each failed setup attempt.
        for _ in range(3):
            coordinator = EcowittDataUpdateCoordinator(hass, entry)
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()
        assert [call.args[1] for call in command.await_args_list] == [
            CMD_READ_MAC,
            CMD_REBOOT,
        ]
        api.return_value.request_loc_allinfo = AsyncMock(
            return_value={"mac": entry.data[CONF_MAC]}
        )
        coordinator.recovery.failures = 2
        with patch.object(
            coordinator,
            "_maybe_update_firmware_info",
            new_callable=AsyncMock,
            return_value={},
        ):
            await coordinator._async_update_data()
        assert coordinator.recovery.failures == 0


async def test_failed_first_refresh_does_not_hide_restart_action(hass, entry):
    await async_setup(hass, {})
    with patch("custom_components.ha_ecowitt_iot.coordinator.API") as api:
        api.return_value.request_loc_allinfo = AsyncMock(side_effect=TimeoutError)
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert hass.services.has_service(DOMAIN, "restart_gateway")
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
