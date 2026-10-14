"""Recovery safety and lifecycle regression tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import Context
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_ecowitt_iot import async_setup
from custom_components.ha_ecowitt_iot.button import EcowittRestartButton
from custom_components.ha_ecowitt_iot.const import CONF_AUTO_RESTART, CONF_MAC, DOMAIN
from custom_components.ha_ecowitt_iot.recovery import (
    RESTART_COOLDOWN,
    GatewayRecovery,
    async_get_recovery,
)
from custom_components.ha_ecowitt_iot.tcp import (
    CMD_READ_MAC,
    CMD_REBOOT,
    GatewayCommandError,
)

MAC = "AA:BB:CC:DD:EE:FF"
MAC_BYTES = bytes.fromhex("aabbccddeeff")


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="GW3000B-WIFIEEFF",
        data={CONF_HOST: "192.0.2.1", CONF_MAC: MAC},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def command():
    with patch(
        "custom_components.ha_ecowitt_iot.recovery.async_command",
        new_callable=AsyncMock,
    ) as mock:
        mock.side_effect = lambda host, code: (
            MAC_BYTES if code == CMD_READ_MAC else b"\x00"
        )
        yield mock


@pytest.fixture(autouse=True)
def no_boot_timer():
    with patch("custom_components.ha_ecowitt_iot.recovery.async_call_later") as timer:
        yield timer


async def test_restart_checks_identity_before_command(
    hass, entry, command, no_boot_timer
):
    recovery = async_get_recovery(hass, entry)
    await recovery.async_restart()
    assert [call.args[1] for call in command.await_args_list] == [
        CMD_READ_MAC,
        CMD_REBOOT,
    ]
    no_boot_timer.assert_called_once()


@pytest.mark.parametrize("mac", ["", "1997", None, "not-a-mac"])
async def test_missing_full_mac_never_contacts_gateway(hass, entry, command, mac):
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MAC: mac})
    with pytest.raises(HomeAssistantError, match="full MAC"):
        await async_get_recovery(hass, entry).async_restart()
    command.assert_not_awaited()


async def test_wrong_device_never_reboots(hass, entry, command):
    command.return_value = bytes.fromhex("001122334455")
    command.side_effect = None
    with pytest.raises(HomeAssistantError, match="MAC does not match"):
        await async_get_recovery(hass, entry).async_restart()
    assert [call.args[1] for call in command.await_args_list] == [CMD_READ_MAC]


async def test_offline_tcp_never_reboots(hass, entry, command):
    command.side_effect = GatewayCommandError("Connection refused")
    with pytest.raises(HomeAssistantError, match="Connection refused"):
        await async_get_recovery(hass, entry).async_restart()
    assert [call.args[1] for call in command.await_args_list] == [CMD_READ_MAC]


async def test_cooldown_survives_manager_recreation(hass, entry, command):
    await GatewayRecovery(hass, entry).async_restart()
    command.reset_mock()
    with pytest.raises(HomeAssistantError, match="cooldown"):
        await GatewayRecovery(hass, entry).async_restart()
    command.assert_not_awaited()


async def test_concurrent_restart_requests_send_one_reboot(hass, entry, command):
    recovery = async_get_recovery(hass, entry)
    results = await asyncio.gather(
        recovery.async_restart(), recovery.async_restart(), return_exceptions=True
    )
    assert results[0] is None
    assert isinstance(results[1], HomeAssistantError)
    assert [call.args[1] for call in command.await_args_list].count(CMD_REBOOT) == 1


@pytest.mark.parametrize("reply", [GatewayCommandError("reply lost"), b"\x01", b""])
async def test_lost_or_rejected_reply_preserves_cooldown(hass, entry, command, reply):
    command.side_effect = [MAC_BYTES, reply]
    recovery = async_get_recovery(hass, entry)
    with pytest.raises(HomeAssistantError):
        await recovery.async_restart()
    command.reset_mock()
    with pytest.raises(HomeAssistantError, match="cooldown"):
        await GatewayRecovery(hass, entry).async_restart()
    command.assert_not_awaited()


async def test_automatic_recovery_is_disabled_by_default(hass, entry, command):
    recovery = async_get_recovery(hass, entry)
    for _ in range(5):
        await recovery.async_poll_failed()
    command.assert_not_awaited()


async def test_auto_restart_counts_failures_across_setup_retries(hass, entry, command):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_AUTO_RESTART: True}
    )
    for _ in range(2):
        await async_get_recovery(hass, entry).async_poll_failed()
    command.assert_not_awaited()
    await async_get_recovery(hass, entry).async_poll_failed()
    assert [call.args[1] for call in command.await_args_list] == [
        CMD_READ_MAC,
        CMD_REBOOT,
    ]
    for _ in range(5):
        await async_get_recovery(hass, entry).async_poll_failed()
    assert [call.args[1] for call in command.await_args_list].count(CMD_REBOOT) == 1


async def test_good_poll_resets_auto_restart_counter(hass, entry, command):
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_AUTO_RESTART: True}
    )
    recovery = async_get_recovery(hass, entry)
    await recovery.async_poll_failed()
    await recovery.async_poll_failed()
    recovery.reset_failures()
    await recovery.async_poll_failed()
    command.assert_not_awaited()


async def test_cooldown_expiry_allows_a_later_restart(hass, entry, command):
    recovery = async_get_recovery(hass, entry)
    with patch(
        "custom_components.ha_ecowitt_iot.recovery.time.time", return_value=100000
    ):
        await recovery.async_restart()
    with patch(
        "custom_components.ha_ecowitt_iot.recovery.time.time",
        return_value=100000 + RESTART_COOLDOWN,
    ):
        await recovery.async_restart()
    assert [call.args[1] for call in command.await_args_list].count(CMD_REBOOT) == 2


async def test_storage_failure_prevents_reboot(hass, entry, command):
    recovery = async_get_recovery(hass, entry)
    with (
        patch.object(recovery._store, "async_save", side_effect=OSError("disk full")),
        pytest.raises(HomeAssistantError, match="Cannot save"),
    ):
        await recovery.async_restart()
    assert [call.args[1] for call in command.await_args_list] == [CMD_READ_MAC]


async def test_restart_action_works_without_a_loaded_coordinator(hass, entry, command):
    await async_setup(hass, {})
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    await hass.services.async_call(
        DOMAIN, "restart_gateway", {"config_entry_id": entry.entry_id}, blocking=True
    )
    assert [call.args[1] for call in command.await_args_list] == [
        CMD_READ_MAC,
        CMD_REBOOT,
    ]


async def test_action_rejects_other_integrations(hass, command):
    other = MockConfigEntry(domain="other", data={})
    other.add_to_hass(hass)
    await async_setup(hass, {})
    with pytest.raises(ServiceValidationError, match="enabled Ecowitt"):
        await hass.services.async_call(
            DOMAIN,
            "restart_gateway",
            {"config_entry_id": other.entry_id},
            blocking=True,
        )
    command.assert_not_awaited()


async def test_restart_action_rejects_non_admin_user(hass, entry, command):
    # Home Assistant makes the first user the owner regardless of group_ids.
    await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("Limited user", group_ids=[])
    assert not user.is_admin
    await async_setup(hass, {})
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "restart_gateway",
            {"config_entry_id": entry.entry_id},
            blocking=True,
            context=Context(user_id=user.id),
        )
    command.assert_not_awaited()


async def test_restart_action_allows_admin_without_entities(hass, entry, command):
    user = await hass.auth.async_create_user("Admin", group_ids=["system-admin"])
    await async_setup(hass, {})
    await hass.services.async_call(
        DOMAIN,
        "restart_gateway",
        {"config_entry_id": entry.entry_id},
        blocking=True,
        context=Context(user_id=user.id),
    )
    assert [call.args[1] for call in command.await_args_list] == [
        CMD_READ_MAC,
        CMD_REBOOT,
    ]


async def test_delayed_refresh_reloads_failed_setup(
    hass, entry, command, no_boot_timer
):
    await async_get_recovery(hass, entry).async_restart()
    callback = no_boot_timer.call_args.args[2]
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as reload:
        await callback(None)
    reload.assert_awaited_once_with(entry.entry_id)


async def test_delayed_refresh_polls_loaded_coordinator(
    hass, entry, command, no_boot_timer
):
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    await async_get_recovery(hass, entry).async_restart()
    callback = no_boot_timer.call_args.args[2]
    await callback(None)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_button_remains_callable_when_http_is_unavailable(hass, entry):
    coordinator = MagicMock()
    coordinator.config_entry = entry
    coordinator.last_update_success = False
    coordinator.recovery.async_restart = AsyncMock()
    button = EcowittRestartButton(coordinator)
    assert button.available
    await button.async_press()
    coordinator.recovery.async_restart.assert_awaited_once()
