"""Helper functions"""
from .const import GOVEE_WRITE_CHAR, GOVEE_SERVICE_UUID


async def rgb_to_hex(red, green, blue) -> str:
    return "{0:02x}{1:02x}{2:02x}".format(red, green, blue)


async def hex_to_rgb(hex_color) -> tuple[int, int, int]:
    red, green, blue = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return red, green, blue


async def ble_get_command(payload) -> bytes:
    checksum = await ble_get_checksum(payload)
    command = payload + checksum
    return bytes.fromhex(command)


async def ble_get_checksum(payload) -> str:
    hex_values = []
    for i in range(0, len(payload), 2):
        substring = payload[i:i + 2]
        byte_value = int(substring, 16)
        hex_values.append(byte_value)

    result = hex_values[0]
    for value in hex_values[1:]:
        result ^= value

    checksum = hex(result)[2:].zfill(2)
    return checksum


async def ble_get_write_characteristic(client) -> str:
    services = client.services
    for service in services:
        if service.uuid == GOVEE_SERVICE_UUID:
            characteristics = service.characteristics
            for characteristic in characteristics:
                if characteristic.uuid == GOVEE_WRITE_CHAR:
                    return characteristic
