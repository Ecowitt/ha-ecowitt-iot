"""Minimal, bounded Ecowitt TCP API commands for HTTP outage recovery."""

from __future__ import annotations

import asyncio
from contextlib import suppress

TCP_PORT = 45000
TCP_TIMEOUT = 10
CMD_READ_MAC = 0x26
CMD_REBOOT = 0x40


class GatewayCommandError(Exception):
    """The gateway did not return a valid TCP API response."""


async def async_command(host: str, command: int) -> bytes:
    """Send a command and validate its complete, one-byte-size response."""
    writer = None
    try:
        async with asyncio.timeout(TCP_TIMEOUT):
            reader, writer = await asyncio.open_connection(host, TCP_PORT)
            writer.write(bytes((0xFF, 0xFF, command, 3, (command + 3) & 0xFF)))
            await writer.drain()
            header = await reader.readexactly(4)
            if header[:3] != bytes((0xFF, 0xFF, command)) or header[3] < 3:
                raise GatewayCommandError("Invalid TCP API response header")
            frame = header + await reader.readexactly(header[3] - 2)
            if (sum(frame[2:-1]) & 0xFF) != frame[-1]:
                raise GatewayCommandError("Invalid TCP API response checksum")
            return frame[4:-1]
    except (OSError, EOFError) as error:
        raise GatewayCommandError(f"TCP API request failed: {error}") from error
    finally:
        if writer is not None:
            writer.close()
            with suppress(OSError, TimeoutError):
                async with asyncio.timeout(1):
                    await writer.wait_closed()
