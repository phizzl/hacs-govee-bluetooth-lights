"""Helper functions"""
import math
from .const import GOVEE_WRITE_CHAR, GOVEE_SERVICE_UUID
from bleak import BleakClient, BleakGATTCharacteristic


def rgb_to_hex(red, green, blue) -> str:
    """Convert an RGB tuple into hex color"""
    return "{0:02x}{1:02x}{2:02x}".format(red, green, blue)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex into an RGB tuple"""
    red, green, blue = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return red, green, blue


def kelvin_to_hex(kelvin: int):
    temp = kelvin / 100
    red, green, blue = 255, 255, 255

    if temp <= 66:
        red = 255
        green = 99.4708025861 * math.log(temp) - 161.1195681661
        if temp <= 19:
            blue = 0
        else:
            blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
        blue = 255

    r, g, b = map(lambda x: max(0, min(x, 255)), [red, green, blue])

    return '{:02x}{:02x}{:02x}'.format(int(r), int(g), int(b))


def ble_get_command(payload: str) -> bytes:
    """Convert a given string payload to a Govee byte command"""
    checksum = ble_get_checksum(payload)
    command = payload + checksum
    return bytes.fromhex(command)


def ble_get_checksum(payload: str) -> str:
    """Calculate the checksum for Govee BLE commands"""
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


def ble_get_write_characteristic(client: BleakClient) -> BleakGATTCharacteristic:
    """Filter the BLE characteristic by a given client"""
    services = client.services
    for service in services:
        if service.uuid == GOVEE_SERVICE_UUID:
            characteristics = service.characteristics
            for characteristic in characteristics:
                if characteristic.uuid == GOVEE_WRITE_CHAR:
                    return characteristic
