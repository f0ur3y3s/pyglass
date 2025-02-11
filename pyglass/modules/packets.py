# 0x06,                # Command ID: Dashboard
# 0x15, 0x00,          # Packet length (0x0015 = 21 bytes)
# seq_id,              # Sequence number
# 0x01,                # Subcommand: Update time/weather
# 0x4F, 0x6F, 0x71, 0x67,  # 32-bit timestamp (e.g. 0x67716F4F)
# 0x98, 0xC9, 0xAC, 0x31, 0x41, 0x19, 0x00, 0x00,  # 64-bit timestamp
# icon,                # Weather icon ID (0x00 - 0x10)
# temperature_c,       # Celsius
# convert_f,           # If 0x01, convert to Fahrenheit
# time_format          # If 0x01, 12h format; else 24h

#  [Command ID][Packet Length][Sequence ID][Subcommand][Data...]

import struct
from pyglass.commands.commands import Commands
from pyglass.utils.logger import Logger
from pyglass.commands.commands import DisplayStatus, ScreenAction

# 0x02 - Possibly enables “anti-shake” functionality.
# 0x03 - Toggles silent mode.
# 0x05 - Subcommand 0x02 sets log level, among others.
# 0x07 - Displays a countdown on the glasses.
# 0x09 - Teleprompter.
# 0x0A - Navigation (RLE for map images).
# 0x0D, 0x0E, 0x0F - Translation functionalities.

from abc import ABC, abstractmethod


class Packet(ABC):
    format = "<BHBB"

    def __init__(
        self,
        cid: int,
        length: int,
        seq_id: int,
        subcommand: int,
        data: bytes,
    ):
        self.cid: int = cid
        self.length: int = length
        self.seq_id: int = seq_id
        self.subcommand: int = subcommand
        self.data: bytes = data

    @abstractmethod
    def pack(self):
        return (
            struct.pack(
                self.format,
                self.cid,
                self.length,
                self.seq_id & 0xFF,
                self.subcommand,
            )
            + self.data
        )

    @classmethod
    def unpack(cls, data: bytes) -> "Packet":
        return cls(*struct.unpack(cls.format, data[:6]), data[6:])


class Heartbeat(Packet):
    format = "<BHBBB"

    def __init__(self, heartbeat: int):
        super().__init__(Commands.BLE_REQ_HEARTBEAT, 0, heartbeat, 0, b"")
        self.length = 6

    def pack(self):
        return struct.pack(
            self.format,
            self.cid,
            self.seq_id & 0xFF,
            self.length,
            self.subcommand,
            self.seq_id,
        )


# Command Information
# Command: 0x4E
# seq (Sequence Number): 0~255
# total_package_num (Total Package Count): 1~255
# current_package_num (Current Package Number): 0~255
# newscreen (Screen Status)
class Text(Packet):
    format = "<BHBBBBB"
    max_chunk_size = 191

    def __init__(
        self,
        seq: int,
        text: str,
    ):
        self.total_package_num = 1  # TODO: calculate this based on length of text
        self.current_page = 0
        self.newscreen = DisplayStatus.NORMAL_TEXT | ScreenAction.NEW_CONTENT
        # data: bytes = text.encode()
        # data = struct.pack(
        #     f"<BBB{len(text)}s",
        #     total_package_num,
        #     current_package_num,
        #     newscreen,
        #     text.encode(),
        # )
        self.data = text.encode()
        self.chunks = [
            self.data[i : i + self.max_chunk_size]
            for i in range(0, len(self.data), self.max_chunk_size)
        ]

        # super().__init__(
        #     Commands.BLE_REQ_EVENAI,
        #     len(data) + 4,
        #     seq,
        #     # total_package_num,
        #     # current_package_num,
        #     # newscreen,
        #     0,
        #     data,
        # )

    def pack(self):
        header = struct.pack(
            self.format,
            self.cid,
            self.seq_id & 0xFF,
            self.total_package_num,
            self.current_package_num,
            self.newscreen,
            0,
            0,
            self.current_page,
        )
        return (
            struct.pack(
                self.format,
                self.cid,
                self.seq_id & 0xFF,
                self.length,
                self.subcommand,
                self.seq_id,
            )
            + self.data
        )


# newscreen is composed of lower 4 bits and upper 4 bits to represent screen status and Even AI mode.
