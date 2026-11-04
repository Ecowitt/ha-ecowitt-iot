"""Exercise the real TCP framing against a local simulated Ecowitt gateway."""

import asyncio

import pytest

from custom_components.ha_ecowitt_iot import tcp

pytestmark = pytest.mark.enable_socket


def response(command, payload):
    body = bytes((command, len(payload) + 3)) + payload
    return b"\xff\xff" + body + bytes((sum(body) & 255,))


async def exchange(monkeypatch, command, reply, *, fragments=False):
    requests = []

    async def gateway(reader, writer):
        try:
            requests.append(await reader.readexactly(5))
            for part in [bytes((byte,)) for byte in reply] if fragments else [reply]:
                writer.write(part)
                await writer.drain()
                await asyncio.sleep(0)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(gateway, "127.0.0.1", 0)
    monkeypatch.setattr(tcp, "TCP_PORT", server.sockets[0].getsockname()[1])
    async with server:
        payload = await tcp.async_command("127.0.0.1", command)
    assert requests == [bytes((255, 255, command, 3, (command + 3) & 255))]
    return payload


@pytest.mark.parametrize(
    ("command", "payload"),
    [(tcp.CMD_READ_MAC, bytes.fromhex("aabbccddeeff")), (tcp.CMD_REBOOT, b"\x00")],
)
async def test_fragmented_valid_response(monkeypatch, command, payload):
    assert (
        await exchange(monkeypatch, command, response(command, payload), fragments=True)
        == payload
    )


@pytest.mark.parametrize(
    "reply",
    [
        b"\xfe\xff\x26\x09" + b"\x00" * 7,
        response(tcp.CMD_REBOOT, b"\x00"),
        b"\xff\xff\x26\x02",
        response(tcp.CMD_READ_MAC, b"123456")[:-1] + b"\x00",
        response(tcp.CMD_READ_MAC, b"123456")[:-3],
    ],
)
async def test_invalid_or_truncated_response(monkeypatch, reply):
    with pytest.raises(tcp.GatewayCommandError):
        await exchange(monkeypatch, tcp.CMD_READ_MAC, reply)


async def test_unresponsive_tcp_has_bounded_timeout(monkeypatch):
    connections = set()

    async def gateway(reader, writer):
        task = asyncio.current_task()
        connections.add(task)
        try:
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            connections.discard(task)

    server = await asyncio.start_server(gateway, "127.0.0.1", 0)
    monkeypatch.setattr(tcp, "TCP_PORT", server.sockets[0].getsockname()[1])
    monkeypatch.setattr(tcp, "TCP_TIMEOUT", 0.05)
    async with server:
        with pytest.raises(tcp.GatewayCommandError, match="TCP API request failed"):
            await asyncio.wait_for(tcp.async_command("127.0.0.1", tcp.CMD_READ_MAC), 1)
    if connections:
        await asyncio.gather(*connections)
