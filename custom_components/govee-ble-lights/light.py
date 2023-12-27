from __future__ import annotations

import asyncio
import math
import logging
import random
import bleak_retry_connector

from bleak import BLEDevice, BleakClient
from typing import List
from homeassistant.components import bluetooth
from homeassistant.components.light import (ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_COLOR_TEMP_KELVIN, ColorMode,
                                            LightEntity)
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, GOVEE_READ_CHAR
from .helper import rgb_to_hex, hex_to_rgb, ble_get_write_characteristic, ble_get_command, kelvin_to_hex

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    light = hass.data[DOMAIN][config_entry.entry_id]
    # bluetooth setup
    ble_device = bluetooth.async_ble_device_from_address(hass, light.address.upper(), False)
    async_add_entities([GoveeBluetoothLight(light, ble_device)])


class GoveeBluetoothLight(LightEntity):
    """Payloads which will be sent to receive the current device status in the corresponding response notification"""
    update_payloads = [
        "aa010000000000000000000000000000000000",  # power status
        "aa040000000000000000000000000000000000",  # brightness
        "aa050100000000000000000000000000000000",  # color and color temperature
    ]

    def __init__(self, light, ble_device: BLEDevice) -> None:
        """Initialize a bluetooth light."""
        self._ble_device = ble_device

        # Set inherited attributes
        self._attr_color_mode = ColorMode.RGB
        self._attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP, ColorMode.BRIGHTNESS}
        self._attr_name = f"Govee Light {ble_device.name}"
        self._attr_unique_id = self._ble_device.address.replace(":", "")
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None
        self._attr_min_color_temp_kelvin = 2000
        self._attr_max_color_temp_kelvin = 6500
        self._attr_rgb_color = None
        self._attr_is_on = False
        self._attr_should_poll = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ble_device.address)},
            name=self._ble_device.name
        )

    async def async_turn_on(self, **kwargs) -> None:
        payloads = ["33010100000000000000000000000000000000"]
        _LOGGER.debug(f"[async_turn_on|%s] Powering on", self._ble_device.address)

        self._attr_is_on = True

        if ATTR_BRIGHTNESS in kwargs:
            brightness_ha = kwargs.get(ATTR_BRIGHTNESS, 255)
            brightness_percent = math.ceil(brightness_ha / 255 * 100)
            brightness = str(math.ceil(64 * (brightness_percent / 100))).zfill(2)
            brightness = "01" if brightness == "00" else brightness
            payload = "3304" + brightness + "00000000000000000000000000000000"
            payloads.append(payload)
            _LOGGER.debug(
                f"[async_turn_on|%s] Setting brightness to %s (%s)",
                self._ble_device.address,
                str(brightness_percent),
                brightness_ha
            )

            self._attr_brightness = brightness_ha

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            hex_color = rgb_to_hex(red, green, blue)
            payload = "33050d" + hex_color.lower() + "00000000000000000000000000"
            payloads.append(payload)
            _LOGGER.debug(
                f"[async_turn_on|%s] Setting color to %s, (%s, %s, %s)",
                self._ble_device.address,
                hex_color,
                red,
                green,
                blue
            )

            self._attr_rgb_color = (red, green, blue)

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
            kelvin_hex = hex(color_temp_kelvin)
            kelvin_hex = kelvin_hex[2:].zfill(4)
            color_hex = kelvin_to_hex(color_temp_kelvin)
            color_rgb = hex_to_rgb(color_hex)
            payload = "33050dffffff" + kelvin_hex + "0000000000000000000000"
            payloads.append(payload)
            _LOGGER.debug(
                f"[async_turn_on|%s] Setting color temperature to %s",
                self._ble_device.address,
                color_temp_kelvin
            )

            self._attr_color_temp_kelvin = color_temp_kelvin
            self._attr_rgb_color = color_rgb

        client = await self._get_connection()
        await self._send_payloads(client, payloads)

    async def async_turn_off(self, **kwargs) -> None:
        payloads = ["33010000000000000000000000000000000000"]
        _LOGGER.debug(f"[async_turn_off|%s] Powering off", self._ble_device.address)

        self._attr_is_on = False

        client = await self._get_connection()
        await self._send_payloads(client, payloads)

    async def async_update(self):
        async def on_notify(client, data):
            response = data.hex()
            _LOGGER.debug(f"[async_update|%s] Update notification \"%s\"", self._ble_device.address, response)
            if not response.startswith("aa"):
                return None

            type = response[2:4]
            if type == "01":
                is_on = response[4:6] == "01"
                _LOGGER.debug(f"[async_update|%s] STATE Powering state %s", self._ble_device.address, str(is_on))

                self._attr_is_on = is_on
            elif type == "04":
                brightness_govee = int(response[4:6], 16)
                brightness_percent = math.ceil(((brightness_govee / 64) * 100))
                brightness = math.ceil((255 / 100) * brightness_percent)
                _LOGGER.debug(
                    f"[async_update|%s] STATE Brightness is %s (%s)",
                    self._ble_device.address,
                    str(brightness_percent),
                    str(brightness)
                )

                self._attr_brightness = brightness
            elif type == "05":
                color_temp_kelvin = int(response[12:16], 16)

                if color_temp_kelvin > 0:
                    color_hex = kelvin_to_hex(color_temp_kelvin)
                else:
                    color_hex = response[6:12]

                color_rgb = hex_to_rgb(color_hex)

                _LOGGER.debug(
                    f"[async_update|%s] STATE Color R: %s, G: %s, B: %s (%s), color temp %s",
                    self._ble_device.address,
                    color_rgb[0],
                    color_rgb[1],
                    color_rgb[2],
                    color_hex,
                    color_temp_kelvin,
                )

                self._attr_rgb_color = color_rgb
                self._attr_color_temp_kelvin = color_temp_kelvin

        await asyncio.sleep(1)
        client = await self._get_connection()
        await client.start_notify(GOVEE_READ_CHAR, on_notify)
        await self._send_payloads(client, self.update_payloads)

    async def _send_payloads(self, client: BleakClient, payloads: List[str]):
        rnd = str(random.randint(1, 9999))

        characteristic = ble_get_write_characteristic(client)
        for payload in payloads:
            command = ble_get_command(payload)
            _LOGGER.debug(f"[_send_payloads|%s/%s] Send command \"%s\"", self._ble_device.address, rnd, command)
            await client.write_gatt_char(characteristic, command)

    async def _get_connection(self) -> BleakClient:
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                _LOGGER.debug(
                    f"[_get_connection|%s] Trying to connect [%s/%s]",
                    self._ble_device.address,
                    (retry_count + 1),
                    max_retries
                )
                client = await bleak_retry_connector.establish_connection(BleakClient, self._ble_device,
                                                                          self._ble_device.address)
                return client
            except Exception as e:
                _LOGGER.warning(f"[_get_connection|%s] Exception: %s", self._ble_device.address, e)
                retry_count += 1
                await asyncio.sleep(0.5)
        else:
            raise Exception(f"[_get_connection|%s] Connection could not be established", self._ble_device.address)
