from __future__ import annotations

import math
import logging

from bleak import BLEDevice
from datetime import timedelta
from homeassistant.components import bluetooth
from homeassistant.components.light import (ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_COLOR_TEMP_KELVIN, ColorMode,
                                            LightEntity)
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .govee.ble_requests import BleLightRequestFactory
from .govee.ble_client import BleClient
from .govee.helper import wait_for_event_with_timeout, kelvin_to_rgb

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=5)


async def async_setup_entry(hass, config_entry, async_add_entities):
    light = hass.data[DOMAIN][config_entry.entry_id]
    # bluetooth setup
    ble_device = bluetooth.async_ble_device_from_address(hass, light.address.upper(), False)
    async_add_entities([GoveeBluetoothLight(ble_device)], update_before_add=True)


class GoveeBluetoothLight(LightEntity):

    def __init__(self, ble_device: BLEDevice) -> None:
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
        self._attr_should_poll = False
        self._attr_icon = "mdi:lightbulb"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ble_device.address)},
            name=self._ble_device.name,
            manufacturer="Govee"
        )

    async def async_turn_on(self, **kwargs) -> None:
        _LOGGER.debug(f"[%s] Powering on", self._ble_device.name)
        power_state_request = BleLightRequestFactory.create_power_state_request(True)
        await BleClient.send_request(self._ble_device, power_state_request)
        self._attr_is_on = True
        self.async_write_ha_state()

        if ATTR_BRIGHTNESS in kwargs:
            brightness_ha = kwargs.get(ATTR_BRIGHTNESS, 255)
            brightness_percent = math.ceil(brightness_ha / 255 * 100)

            _LOGGER.debug(f"[%s] Setting brightness to %s (%s)", self._ble_device.name, brightness_percent)
            brightness_request = BleLightRequestFactory.create_brightness_request(brightness_percent)
            await BleClient.send_request(self._ble_device, brightness_request)
            self._attr_brightness = brightness_ha
            self.async_write_ha_state()

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)

            _LOGGER.debug(f"[%s] Setting color to (%s, %s, %s)", self._ble_device.name, red, green, blue)
            color_request = BleLightRequestFactory.create_color_request((red, green, blue))
            await BleClient.send_request(self._ble_device, color_request)
            self._attr_rgb_color = (red, green, blue)
            self._attr_color_temp_kelvin = None
            self.async_write_ha_state()

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

            _LOGGER.debug(f"[%s] Setting color temperature to %s kelvin", self._ble_device.name, color_temp_kelvin)
            color_temp_request = BleLightRequestFactory.create_color_temperature_request(color_temp_kelvin)
            await BleClient.send_request(self._ble_device, color_temp_request)
            self._attr_rgb_color = kelvin_to_rgb(color_temp_kelvin)
            self._attr_color_temp_kelvin = color_temp_kelvin
            self.async_write_ha_state()

        self._attr_should_poll = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        _LOGGER.debug(f"[%s] Powering on", self._ble_device.name)
        power_state_request = BleLightRequestFactory.create_power_state_request(False)
        event = await BleClient.send_request(self._ble_device, power_state_request)
        await wait_for_event_with_timeout(event)

        self._attr_should_poll = True

    async def async_update(self):
        _LOGGER.debug(f"[%s] Update triggered", self._ble_device.name)

        power_state_status_request = BleLightRequestFactory.create_power_state_status_request()
        event = await BleClient.send_request(self._ble_device, power_state_status_request)
        if await wait_for_event_with_timeout(event):
            self._attr_is_on = event.notify_response

        brightness_status_request = BleLightRequestFactory.create_brightness_status_request()
        event = await BleClient.send_request(self._ble_device, brightness_status_request)
        if await wait_for_event_with_timeout(event):
            brightness_percent = event.notify_response
            brightness = math.ceil((255 / 100) * brightness_percent)
            self._attr_brightness = brightness

        color_status_request = BleLightRequestFactory.create_color_status_request()
        event = await BleClient.send_request(self._ble_device, color_status_request)
        if await wait_for_event_with_timeout(event):
            color = event.notify_response
            self._attr_rgb_color = color.color_rgb
            self._attr_color_temp_kelvin = color.color_temp_kelvin

        self._attr_should_poll = False

        _LOGGER.debug(
            f"[%s] Power state: %s | Brightness: %s | Color: %s | Color temperature %s",
            self._ble_device.name,
            self._attr_is_on,
            self._attr_brightness,
            self._attr_rgb_color,
            self._attr_color_temp_kelvin
        )
