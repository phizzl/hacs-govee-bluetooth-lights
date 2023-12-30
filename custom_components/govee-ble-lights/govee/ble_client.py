import bleak_retry_connector
import logging

from typing import Dict
from bleak import BLEDevice, BleakClient, BleakGATTCharacteristic
from .ble_requests import BleRequest
from .const import GOVEE_READ_CHAR, GOVEE_WRITE_CHAR, GOVEE_SERVICE_UUID
from .helper import ResponseEvent

_LOGGER = logging.getLogger(__name__)


class BleClient:
    _ble_write_characteristic: Dict[str, BleakGATTCharacteristic] = {}

    @staticmethod
    async def send_request(device: BLEDevice, request: BleRequest) -> ResponseEvent:
        event = ResponseEvent()
        event.request = request
        event.device = device

        client = await BleClient._get_client(device)

        async def on_notify(characteristic: BleakGATTCharacteristic, data: bytes) -> None:
            _LOGGER.debug(
                f"[%s] Received notification \"%s\" for %s",
                client.address,
                data.hex(),
                device.name
            )

            event.response = data
            await client.stop_notify(characteristic.uuid)
            if request.notify_callback is not None:
                event.notify_response = request.notify_callback(event)
            event.set()

        await client.start_notify(GOVEE_READ_CHAR, on_notify)
        write_characteristic = BleClient._get_write_characteristic(client)

        _LOGGER.debug(
            f"[%s] Write payload \"%s\" for %s",
            client.address,
            request.payload.hex(),
            device.name
        )
        await client.write_gatt_char(write_characteristic, request.payload)

        return event

    @staticmethod
    async def _get_client(device: BLEDevice) -> BleakClient:
        def ble_on_disconnect(ble_client: BleakClient) -> None:
            _LOGGER.debug(f"[%s] Disconnected from %s", ble_client.address, device.name)

        _LOGGER.debug(f"[%s] Connect to %s", device.address, device.name)
        client = await bleak_retry_connector.establish_connection(
            BleakClient,
            device,
            device.name,
            ble_on_disconnect,
            20
        )

        return client

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
