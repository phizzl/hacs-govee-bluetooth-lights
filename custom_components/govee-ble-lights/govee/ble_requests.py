import math
from typing import Tuple, Callable, Optional, Any
from .helper import rgb_to_hex, ResponseEvent, ResponseProcessor


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


def ble_get_payload(command: str) -> bytes:
    """Convert a given string payload to a Govee byte command"""
    checksum = ble_get_checksum(command)
    payload = command + checksum
    return bytes.fromhex(payload)


class BleRequest:
    """
    _payload: bytes - Contains the request data (including checksum)
    """
    _payload: bytes

    _notify_callback: Optional[Callable]

    def __init__(self, payload: bytes, notify_callback: Optional[Callable[[ResponseEvent], Any]] = None):
        self._payload = payload
        self._notify_callback = notify_callback

    @property
    def payload(self) -> bytes:
        return self._payload

    @property
    def notify_callback(self) -> Optional[Callable]:
        return self._notify_callback


class BleLightRequestFactory:
    @staticmethod
    def create_power_state_request(power_on: bool) -> BleRequest:
        if power_on:
            command = "33010100000000000000000000000000000000"
        else:
            command = "33010000000000000000000000000000000000"
        return BleRequest(ble_get_payload(command))

    @staticmethod
    def create_brightness_request(brightness_percent: int) -> BleRequest:
        if not 1 <= brightness_percent <= 100:
            raise ValueError("brightness_percent must be between 1 and 100")

        brightness = str(math.ceil(64 * (brightness_percent / 100))).zfill(2)
        brightness = "01" if brightness == "00" else brightness
        command = "3304" + brightness + "00000000000000000000000000000000"
        return BleRequest(ble_get_payload(command))

    @staticmethod
    def create_color_request(colors_rgb: Tuple[int, int, int]) -> BleRequest:
        if not all(0 <= color <= 255 for color in colors_rgb):
            raise ValueError("All values in colors_rgb must be between 0 and 255")

        red, green, blue = colors_rgb
        hex_color = rgb_to_hex(red, green, blue)
        command = "33050d" + hex_color.lower() + "00000000000000000000000000"
        return BleRequest(ble_get_payload(command))

    @staticmethod
    def create_color_temperature_request(color_temp_kelvin: int) -> BleRequest:
        if not 2000 <= color_temp_kelvin <= 6500:
            raise ValueError("color_temp_kelvin must be between 2000 and 6500")

        kelvin_hex = hex(color_temp_kelvin)
        kelvin_hex = kelvin_hex[2:].zfill(4)
        command = "33050dffffff" + kelvin_hex + "0000000000000000000000"
        return BleRequest(ble_get_payload(command))



    @staticmethod
    def create_power_state_status_request() -> BleRequest:
        command = "aa010000000000000000000000000000000000"
        return BleRequest(ble_get_payload(command), ResponseProcessor.process_power_state_status_request)



    @staticmethod
    def create_brightness_status_request() -> BleRequest:
        command = "aa040000000000000000000000000000000000"
        return BleRequest(ble_get_payload(command), ResponseProcessor.process_brightness_status_request)

    @staticmethod
    def create_color_status_request() -> BleRequest:
        command = "aa050100000000000000000000000000000000"
        return BleRequest(ble_get_payload(command), ResponseProcessor.process_color_status_request)
