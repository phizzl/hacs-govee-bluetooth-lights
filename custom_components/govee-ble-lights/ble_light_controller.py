import math
import logging
import re
import asyncio
import random
from bleak import BleakClient, BLEDevice
import bleak_retry_connector
from .const import GOVEE_READ_CHAR, GOVEE_WRITE_CHAR

_LOGGER = logging.getLogger(__name__)

class BleLightController:
    def __init__(self, device: BLEDevice):
        self._device = device
        self._connection = None
        self._characteristic = None

    async def power_on(self) -> None:
        _LOGGER.info(f"['{self._device.address}] Turn power on")
        command = await self._get_command("33010100000000000000000000000000000000")
        await self._send_command(command)

    async def power_off(self) -> None:
        _LOGGER.info(f"['{self._device.address}] Turn power off")
        command = await self._get_command("33010000000000000000000000000000000000")
        await self._send_command(command)

    async def is_power_on(self) -> bool:
        """Get the current power status of the light"""
        _LOGGER.info(f"['{self._device.address}] Ask if power is on")
        command = await self._get_command("aa010000000000000000000000000000000000")
        response = await self._send_command(command, True)
        return response.hex().startswith("aa0101")

    async def set_brightness(self, percent) -> None:
        if percent < 1 or percent > 100:
            raise ValueError("Percent must be between 1 and 100")

        _LOGGER.info(f"['{self._device.address}] Set brightness to {percent}%")
        brightness = str(math.ceil(64 * (percent / 100))).zfill(2)
        brightness = "01" if brightness == "00" else brightness
        payload = "3304" + brightness + "00000000000000000000000000000000"
        command = await self._get_command(payload)
        await self._send_command(command)

    async def get_brightness(self) -> int:
        """Get the current brightness of the light"""
        _LOGGER.info(f"['{self._device.address}] Ask about its current brightness")
        command = await self._get_command("aa040000000000000000000000000000000000")
        response = await self._send_command(command, True)
        brightness = int(response.hex()[4:6])
        percent = math.ceil(((brightness / 64) * 100))
        return percent

    async def set_color(self, color) -> None:
        if not re.match(r'^(?:[0-9a-fA-F]{3}){1,2}$', color) or len(color) != 6:
            raise ValueError("Color must be in hex format")

        _LOGGER.info(f"['{self._device.address}] Set color to #{color}")
        payload = "33050d" + color.lower() + "00000000000000000000000000"
        command = await self._get_command(payload)
        await self._send_command(command)

    async def get_color(self) -> str:
        """Get the current color of the light"""
        _LOGGER.info(f"['{self._device.address}] Ask about its current color")
        command = await self._get_command("aa050100000000000000000000000000000000")
        response = await self._send_command(command, True)
        return response.hex()[6:12]

    async def set_color_temperature(self, kelvin) -> None:
        if kelvin < 2700:
            kelvin = 2700
        elif kelvin > 6500:
            kelvin = 6500

        _LOGGER.info(f"['{self._device.address}] Set color temperature to {kelvin}k")
        kelvin_hex = hex(kelvin)
        kelvin_hex = kelvin_hex[2:].zfill(4)
        payload = "33050dffffff" + kelvin_hex + "0000000000000000000000"
        command = await self._get_command(payload)
        await self._send_command(command)

    async def get_color_temperature(self) -> int:
        """Get the current color temperature of the light"""
        _LOGGER.info(f"['{self._device.address}] Ask about its current color temperature")
        command = await self._get_command("aa050100000000000000000000000000000000")
        response = await self._send_command(command, True)
        color_temp = int(response.hex()[12:16], 16)
        return color_temp

    async def _send_command(self, command, wait_for_notify=False):
        client = await self._get_connection()
        rnd = str(random.randint(1, 9999))

        if wait_for_notify:
            response_future = asyncio.get_event_loop().create_future()

            async def on_notify(client, data):
                _LOGGER.info(f"['{self._device.address}'/{rnd}] on_notify(): {data.hex()}")
                if not response_future.done():
                    response_future.set_result(data)

            await client.start_notify(GOVEE_READ_CHAR, on_notify)

        characteristic = await self._get_write_characteristic(client)
        _LOGGER.debug(f"['{self._device.address}'/{rnd}] Send command \"{command}\"")
        await client.write_gatt_char(characteristic, command)

        if wait_for_notify:
            return await response_future

    async def _get_write_characteristic(self, client) -> str:
        if not self._characteristic is None:
            return self._characteristic

        services = client.services
        for service in services:
            if service.uuid == "00010203-0405-0607-0809-0a0b0c0d1910":
                characteristics = service.characteristics
                for characteristic in characteristics:
                    if characteristic.uuid == GOVEE_WRITE_CHAR:
                        self._characteristic = characteristic
                        return characteristic

    async def _get_connection(self) -> BleakClient:
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                _LOGGER.debug(f"['{self._device.address}] Trying to connect [{retry_count + 1}/{max_retries}]")
                client = await bleak_retry_connector.establish_connection(BleakClient, self._device, self._device.address)
                return client
            except Exception as e:
                _LOGGER.debug(f"['{self._device.address}] Exception: {e}")
                retry_count += 1
                await asyncio.sleep(0.5)
        else:
            raise Exception(f"['{self._device.address}] Connection could not be established")

    async def _get_command(self, payload) -> bytes:
        checksum = await self._get_checksum(payload)
        command = payload + checksum
        return bytes.fromhex(command)

    async def _get_checksum(self, payload) -> str:
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
