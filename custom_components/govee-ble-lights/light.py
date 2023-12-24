from __future__ import annotations
from typing import Any

import logging
_LOGGER = logging.getLogger(__name__)

from enum import IntEnum
import time
import bleak_retry_connector

from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.light import (ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_COLOR_TEMP_KELVIN, ColorMode, LightEntity)

from .const import DOMAIN

UUID_CONTROL_CHARACTERISTIC = '00010203-0405-0607-0809-0a0b0c0d2b11'

class LedCommand(IntEnum):
    """ A control command packet's type. """
    POWER      = 0x01
    BRIGHTNESS = 0x04
    COLOR      = 0x05

class LedMode(IntEnum):
    """
    The mode in which a color change happens in.
    
    Currently only manual is supported.
    """
    MANUAL     = 0x02
    MICROPHONE = 0x06
    SCENES     = 0x05 

async def async_setup_entry(hass, config_entry, async_add_entities):
    light = hass.data[DOMAIN][config_entry.entry_id]
    #bluetooth setup
    ble_device = bluetooth.async_ble_device_from_address(hass, light.address.upper(), False)
    async_add_entities([GoveeBluetoothLight(light, ble_device)])

class GoveeBluetoothLight(LightEntity):
    def __init__(self, light, ble_device) -> None:
        """Initialize a bluetooth light."""
        self._mac = light.address
        self._ble_device = ble_device

        # Set inherited attributes
        self._attr_color_mode = ColorMode.RGB
        self._attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP, ColorMode.BRIGHTNESS}
        self._attr_name = f"Govee Light {ble_device['device_name']}"
        self._attr_unique_id = self._mac.replace(":", "")
        self._attr_brightness = None
        self._attr_color_temp_kelvin = None
        self._attr_rgb_color = None
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs) -> None:
        await self._sendBluetoothData(LedCommand.POWER, [0x1])
        self._state = True

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            await self._sendBluetoothData(LedCommand.BRIGHTNESS, [brightness])
            self._brightness = brightness

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            await self._sendBluetoothData(LedCommand.COLOR, [LedMode.MANUAL, red, green, blue])

    async def async_turn_off(self, **kwargs) -> None:
        await self._sendBluetoothData(LedCommand.POWER, [0x0])
        self._state = False

    async def _connectBluetooth(self) -> BleakClient:
        client = await bleak_retry_connector.establish_connection(BleakClient, self._ble_device, self.unique_id)
        return client

    async def _sendBluetoothData(self, cmd, payload):
        if not isinstance(cmd, int):
            raise ValueError('Invalid command')
        if not isinstance(payload, bytes) and not (isinstance(payload, list) and all(isinstance(x, int) for x in payload)):
            raise ValueError('Invalid payload')
        if len(payload) > 17:
            raise ValueError('Payload too long')

        cmd = cmd & 0xFF
        payload = bytes(payload)

        frame = bytes([0x33, cmd]) + bytes(payload)
        # pad frame data to 19 bytes (plus checksum)
        frame += bytes([0] * (19 - len(frame)))
        
        # The checksum is calculated by XORing all data bytes
        checksum = 0
        for b in frame:
            checksum ^= b
        
        frame += bytes([checksum & 0xFF])
        client = await self._connectBluetooth()
        await client.write_gatt_char(UUID_CONTROL_CHARACTERISTIC, frame, False)
