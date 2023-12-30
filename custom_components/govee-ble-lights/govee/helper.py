import math
from typing import Optional, Any, Tuple, Dict, Union
from asyncio import Event
from bleak import BLEDevice


def rgb_to_hex(red: int, green: int, blue: int) -> str:
    """Convert an RGB tuple into hex color"""
    return "{0:02x}{1:02x}{2:02x}".format(red, green, blue)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex into an RGB tuple"""
    red, green, blue = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return red, green, blue


def kelvin_to_rgb(kelvin: int) -> Tuple[int, int, int]:
    temp = kelvin / 100

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

    return math.ceil(r), math.ceil(g), math.ceil(b)


class ResponseEvent(Event):
    device: BLEDevice
    request: bytes
    response: Optional[bytes]
    notify_response: Optional[Any]

    def __init__(self):
        super().__init__()
        self.response = None
        self.notify_response = None


class ResponseProcessor:
    @staticmethod
    def process_power_state_status_request(event: ResponseEvent) -> Optional[bool]:
        response = event.response.hex()
        if not response.startswith("aa01"):
            return None

        return response[4:6] == "01"

    @staticmethod
    def process_brightness_status_request(event: ResponseEvent) -> Optional[int]:
        response = event.response.hex()
        if not response.startswith("aa04"):
            return None

        brightness = response[4:6]
        if brightness.isdigit():
            brightness = int(brightness)
        else:
            brightness = int(response[4:6], 16)

        brightness_percent = math.ceil(((brightness / 64) * 100))

        return brightness_percent

    @staticmethod
    def process_color_status_request(event: ResponseEvent) -> Optional[Dict[str, Union[Tuple[int, int, int], int]]]:
        response = event.response.hex()
        if not response.startswith("aa05"):
            return None

        color_temp_kelvin = int(response[12:16], 16)

        if color_temp_kelvin > 0:
            color_rgb = kelvin_to_rgb(color_temp_kelvin)
        else:
            color_rgb = hex_to_rgb(response[6:12])

        return {"color_rgb": color_rgb, "color_temp_kelvin": color_temp_kelvin}


