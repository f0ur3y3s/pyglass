import asyncio
from pprint import pformat
from bleak import BleakClient, BleakScanner, BleakError, BleakGATTCharacteristic
from struct import pack
import time
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
        self._evenai_seq: int = 0
        self._received_ack: bool = False
        self._last_device_order: DeviceOrders = None
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
                self.clog.debug("Received EvenAI data.")

                if len(data) > 1 and data[1] == DeviceOrders.ORDER_RECIEVED:
                    self._received_ack = True
            case Commands.BLE_REQ_DEVICE_ORDER:
                self.clog.debug("Received device order.")
                order = data[1]
                self._last_device_order = order
                self.clog.debug(f"Order: {DeviceOrders(order).name}")
                if order == DeviceOrders.DISPLAY_COMPLETE:
                    self._received_ack = True
            case _:
                self.clog.debug("Received unknown command.")
                try:
                    self.clog.debug(f"{Commands(cmd).name}")
                except ValueError:
                    self.clog.debug(f"Unknown command: {cmd}")
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

    async def send_text(
        self,
        text,
        new_screen: int = 1,
        pos: int = 0,
        current_page: int = 1,
        max_pages: int = 1,
    ):
        lines = self._format_text_lines(text)
        total_pages = (len(lines) + 4) // 5  # 5 lines per page

        if len(lines) <= 3:
            # Special formatting for short messages
            display_text = "\n\n" + "\n".join(lines)
            # Send initial display
            success = await self._send_text_packet(
                display_text,
                new_screen=1,
                status=DisplayStatus.NORMAL_TEXT,
                current_page=1,
                max_pages=1,
            )
            if not success:
                return False

            # Wait 3 seconds then send final display
            await asyncio.sleep(3)
            success = await self._send_text_packet(
                display_text,
                new_screen=1,
                status=DisplayStatus.FINAL_TEXT,
                current_page=1,
                max_pages=1,
            )
            return success

        elif len(lines) <= 5:
            # Format for 4-5 lines
            padding = "\n" if len(lines) == 4 else ""
            display_text = padding + "\n".join(lines)

            # Send initial display
            success = await self._send_text_packet(
                display_text,
                new_screen=1,
                status=DisplayStatus.NORMAL_TEXT,
                current_page=1,
                max_pages=1,
            )
            if not success:
                return False

            # Wait 3 seconds then send final display
            await asyncio.sleep(3)
            success = await self._send_text_packet(
                display_text,
                new_screen=1,
                status=DisplayStatus.FINAL_TEXT,
                current_page=1,
                max_pages=1,
            )
            return success

        else:
            # Multi-page display
            current_page = 1
            start_idx = 0

            while start_idx < len(lines):
                page_lines = lines[start_idx : start_idx + 5]
                display_text = "\n".join(page_lines)

                is_last_page = start_idx + 5 >= len(lines)
                status = (
                    DisplayStatus.FINAL_TEXT
                    if is_last_page
                    else DisplayStatus.NORMAL_TEXT
                )

                success = await self._send_text_packet(
                    display_text,
                    new_screen=1,
                    status=status,
                    current_page=current_page,
                    max_pages=total_pages,
                )
                if not success:
                    return False

                if not is_last_page:
                    await asyncio.sleep(5)  # Wait 5 seconds between pages

                start_idx += 5
                current_page += 1

            return True

    def _format_text_lines(self, text):
        """Format text into lines that fit the display"""
        # Split text into paragraphs
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        lines = []

        for paragraph in paragraphs:
            # Simple line wrapping at ~40 characters
            # In real implementation, should use proper text measurement
            while len(paragraph) > 40:
                space_idx = paragraph.rfind(" ", 0, 40)
                if space_idx == -1:
                    space_idx = 40
                lines.append(paragraph[:space_idx])
                paragraph = paragraph[space_idx:].strip()
            if paragraph:
                lines.append(paragraph)

        return lines

    async def _send_text_packet(
        self, text, new_screen, status, current_page, max_pages
    ):
        """Send a single text packet with proper formatting"""
        text_bytes = text.encode("utf-8")
        max_chunk_size = 191

        chunks = [
            text_bytes[i : i + max_chunk_size]
            for i in range(0, len(text_bytes), max_chunk_size)
        ]

        # Send to Left first
        for i, chunk in enumerate(chunks):
            self._received_ack = False
            header = pack(
                ">BBBBBBBB",
                Commands.BLE_REQ_EVENAI,
                self._evenai_seq & 0xFF,
                len(chunks),
                i,
                status | new_screen,  # Combine status and new_screen
                0,  # pos high byte
                0,  # pos low byte
                current_page,
            )
            packet = header + bytes([max_pages]) + chunk

            await self.left.write_gatt_char(UART_TX_CHAR_UUID, packet)
            if not await self._wait_for_display_complete(timeout=2.0):
                return False

            await asyncio.sleep(0.1)

        # Send to Right after Left completes
        for i, chunk in enumerate(chunks):
            self._received_ack = False
            header = pack(
                ">BBBBBBBB",
                Commands.BLE_REQ_EVENAI,
                self._evenai_seq & 0xFF,
                len(chunks),
                i,
                status | new_screen,
                0,
                0,
                current_page,
            )
            packet = header + bytes([max_pages]) + chunk

            await self.right.write_gatt_char(UART_TX_CHAR_UUID, packet)
            if not await self._wait_for_display_complete(timeout=2.0):
                return False

            await asyncio.sleep(0.1)

        self._evenai_seq += 1
        return True

    async def _wait_for_display_complete(self, timeout=2.0):
        """Wait for display complete status"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._received_ack:
                return True
            await asyncio.sleep(0.1)
        return False
