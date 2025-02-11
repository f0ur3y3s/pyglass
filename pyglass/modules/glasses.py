import asyncio
from pprint import pformat
from bleak import BleakClient, BleakScanner, BleakError, BleakGATTCharacteristic
from struct import pack
from pyglass.modules.logger import Logger
from pyglass.modules.commands import Commands, DeviceOrders, DisplayStatus

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write
UART_RX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Read/Notify


class Lens:
    # might separate the lenses into their own classes
    pass


class Glasses:
    def __init__(self):
        self.left: BleakClient = None
        self.right: BleakClient = None
        self.both_connected: bool = False
        self.heartbeat_seq: int = 0
        self.flog, self.clog = Logger().get_loggers()

    async def scan(self, timeout=10):
        self.clog.debug("Starting scan")

        try:
            await asyncio.wait_for(self._scan_loop(), timeout=timeout)
        except asyncio.TimeoutError:
            self.clog.warning("Scan timed out before finding both devices.")

    async def _scan_loop(self):
        while True:
            devices = await BleakScanner.discover()

            for device in devices:
                if not device.name:
                    continue

                lower_name = str(device.name).lower()

                if "_l_" in lower_name and "even" in lower_name:
                    self.clog.info(f"Found left device: {device.name}")
                    self.left = BleakClient(device)
                elif "_r_" in lower_name and "even" in lower_name:
                    self.clog.info(f"Found right device: {device.name}")
                    self.right = BleakClient(device)

            if self.left and self.right:
                self.clog.info("Found both devices.")
                break

    async def connect(self, scan: bool = False):
        if not scan and (not self.left or not self.right):
            self.clog.error("Cannot connect without both devices.")

        if scan:
            self.clog.debug("Scanning for devices before connecting.")
            await self.scan()

        try:
            await asyncio.wait_for(self._connect_loop(), timeout=10)
        except asyncio.TimeoutError:
            self.clog.error("Connection timed out.")
            raise

    async def _connect_loop(self):
        self.clog.debug("Connecting to left device.")
        await self.left.connect()

        self.clog.debug("Connecting to right device.")
        await self.right.connect()

        await self._initialize()
        self.clog.info("Connected to both devices.")
        self.both_connected = True
        self.heartbeat_seq = 0

    async def disconnect(self):
        if self.left:
            await self.left.disconnect()
            self.clog.info("Disconnected from left device.")

        if self.right:
            await self.right.disconnect()
            self.clog.info("Disconnected from right device.")

        self.clog.info("Disconnected from both devices.")

    async def _initialize(self):
        init_data = bytes([Commands.BLE_REQ_INIT, 0x01])
        await self.left.write_gatt_char(UART_TX_CHAR_UUID, init_data)
        await self.right.write_gatt_char(UART_TX_CHAR_UUID, init_data)
        await self.left.start_notify(UART_RX_CHAR_UUID, self._notification_handler)
        await self.right.start_notify(UART_RX_CHAR_UUID, self._notification_handler)

    async def _notification_handler(
        self,
        sender: BleakGATTCharacteristic,
        data: bytearray,
    ):
        if not self.both_connected:
            self.clog.debug("Waiting for both devices to connect.")
            await self.connect()

        self.clog.debug(pformat(data))

        cmd = data[0]

        match cmd:
            case Commands.BLE_REQ_HEARTBEAT:
                self.clog.debug("Received heartbeat.")
            case Commands.BLE_REQ_TRANSFER_MIC_DATA:
                self.clog.debug("Received mic data.")
                self.clog.debug(data[1:].hex())
            case Commands.BLE_REQ_EVENAI:
                self.clog.debug("Received AI data.")
            case Commands.BLE_REQ_DEVICE_ORDER:
                self.clog.debug("Received device order.")
            case _:
                self.clog.debug("Received unknown command.")
                self.clog.debug(data.hex())

    async def send_heartbeat(self):
        if not self.both_connected:
            self.clog.error("Cannot send heartbeat without both devices connected.")
            await self.connect()
            return

        length = 6
        data = pack(
            "BBBBBB",
            Commands.BLE_REQ_HEARTBEAT,
            length & 0xFF,
            (length >> 8) & 0xFF,
            self.heartbeat_seq % 0xFF,
            0x04,
            self.heartbeat_seq % 0xFF,
        )
        self.heartbeat_seq += 1

        await self.left.write_gatt_char(UART_TX_CHAR_UUID, data)
        await self.right.write_gatt_char(UART_TX_CHAR_UUID, data)
        self.clog.debug("Sent heartbeat.")
