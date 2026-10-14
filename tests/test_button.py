"""End-to-end entity recovery while normal sensor entities are unavailable."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_ecowitt_iot.const import CONF_MAC, DOMAIN
from custom_components.ha_ecowitt_iot.tcp import CMD_READ_MAC, CMD_REBOOT


async def test_restart_button_stays_available_through_http_outage(hass):
    mac = "aa:bb:cc:dd:ee:ff"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GW3000B-WIFIEEFF",
        data={CONF_HOST: "192.0.2.1", CONF_MAC: mac},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.ha_ecowitt_iot.coordinator.API") as api,
        patch(
            "custom_components.ha_ecowitt_iot.recovery.async_command",
            new_callable=AsyncMock,
        ) as command,
        patch("custom_components.ha_ecowitt_iot.recovery.async_call_later"),
    ):
        api.return_value.sensor_info = {}
        api.return_value.request_loc_allinfo = AsyncMock(
            return_value={"mac": mac, "ver": "GW3000B_V1.2.4", "tempf": 52.5}
        )
        api.return_value.request_firmware_update_info = AsyncMock(return_value={})
        api.return_value.request_firmware_update_check = AsyncMock(return_value={})
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        button_id = registry.async_get_entity_id(
            "button", DOMAIN, f"{entry.entry_id}_restart"
        )
        assert button_id is not None
        api.return_value.request_loc_allinfo.side_effect = TimeoutError
        coordinator = hass.data[DOMAIN][entry.entry_id]
        for _ in range(3):
            await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert not coordinator.last_update_success
        assert hass.states.get(button_id).state != STATE_UNAVAILABLE
        sensors = [
            entity.entity_id
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
            if entity.domain == "sensor"
        ]
        assert sensors and all(
            hass.states.get(entity_id).state == STATE_UNAVAILABLE
            for entity_id in sensors
        )
        command.side_effect = [bytes.fromhex("aabbccddeeff"), b"\x00"]
        await hass.services.async_call(
            "button", "press", {"entity_id": button_id}, blocking=True
        )
        assert [call.args[1] for call in command.await_args_list] == [
            CMD_READ_MAC,
            CMD_REBOOT,
        ]
