import asyncio

import logging

from typing import Dict
from bleak import BLEDevice, BleakClient, BleakGATTCharacteristic, BleakError
from .ble_requests import BleRequest
from .const import GOVEE_READ_CHAR, GOVEE_WRITE_CHAR, GOVEE_SERVICE_UUID
from .helper import ResponseEvent

_LOGGER = logging.getLogger(__name__)

MAX_CONNECTION_RETRIES = 12
CONNECTION_RETRY_DELAY = 5
MAX_SEND_RETRIES = 2


class BleClient:
    _ble_write_characteristic: Dict[str, BleakGATTCharacteristic] = {}
    _connections: Dict[str, BleakClient] = {}
    _connection_events: Dict[str, ResponseEvent] = {}

    @staticmethod
    async def send_request(device: BLEDevice, request: BleRequest) -> ResponseEvent:
        counter = 0
        while counter < MAX_SEND_RETRIES:
            try:
                response = await BleClient._send_request_to_device(device, request)
                return response
            except BleakError as e:
                counter += 1
                _LOGGER.warning(
                    f"[%s] An exception occurred while sending request: %s (%s/%s)",
                    device.address,
                    e,
                    counter,
                    MAX_SEND_RETRIES
                )

    @staticmethod
    async def _send_request_to_device(device: BLEDevice, request: BleRequest) -> ResponseEvent:
        """If a callback is given always create a new connection, else try to reuse existing connections"""
        if request.notify_callback is None:
            if device.address in BleClient._connections and BleClient._connections.get(device.address).is_connected:
                client = BleClient._connections.get(device.address)
            else:
                client = await BleClient._get_client(device)
                BleClient._connections[device.address] = client
        else:
            client = await BleClient._get_client(device)

        event = ResponseEvent()
        event.request = request
        event.device = device
        BleClient._connection_events[device.address] = event

        if request.notify_callback is not None:
            async def on_notify(characteristic: BleakGATTCharacteristic, data: bytes) -> None:
                _LOGGER.debug(
                    f"[%s] Received notification \"%s\" for %s",
                    client.address,
                    data.hex(),
                    device.name
                )

                event.response = data
                event.notify_response = request.notify_callback(event)
                event.set()

                await client.disconnect()

            await client.start_notify(GOVEE_READ_CHAR, on_notify)

        _LOGGER.debug(
            f"[%s] Write payload \"%s\" for %s",
            client.address,
            request.payload.hex(),
            device.name
        )

        write_characteristic = BleClient._get_write_characteristic(client)
        await client.write_gatt_char(write_characteristic, request.payload)

        if request.notify_callback is None:
            event.set()

        return event

    @staticmethod
    async def _get_client(device: BLEDevice) -> BleakClient:
        def ble_on_disconnect(ble_client: BleakClient) -> None:
            _LOGGER.debug(f"[%s] Disconnected from %s", ble_client.address, device.name)

        _LOGGER.debug(f"[%s] Connect to %s", device.address, device.name)
        connection_try_counter = 0
        while connection_try_counter < MAX_CONNECTION_RETRIES:
            try:
                connection_try_counter += 1
                client = BleakClient(device, ble_on_disconnect)
                await client.connect()

                _LOGGER.debug(
                    f"[%s] Connected (%s/%s)",
                    device.address,
                    connection_try_counter,
                    MAX_CONNECTION_RETRIES
                )

                return client
            except Exception as e:
                _LOGGER.warning(
                    f"[%s] Failed to connect (%s/%s): %s",
                    device.address,
                    connection_try_counter,
                    MAX_CONNECTION_RETRIES,
                    e
                )
                await asyncio.sleep(CONNECTION_RETRY_DELAY)

        raise Exception(f"Could not connect to {device.address}")

    @staticmethod
    def _get_write_characteristic(client: BleakClient) -> BleakGATTCharacteristic:
        if client.address in BleClient._ble_write_characteristic:
            return BleClient._ble_write_characteristic.get(client.address)

        services = client.services
        for service in services:
            if service.uuid == GOVEE_SERVICE_UUID:
                characteristics = service.characteristics
                for characteristic in characteristics:
                    if characteristic.uuid == GOVEE_WRITE_CHAR:
                        BleClient._ble_write_characteristic[client.address] = characteristic
                        return characteristic

        raise Exception(f"[%s] Characteristic not found", client.address)
