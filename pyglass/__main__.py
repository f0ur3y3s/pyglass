import asyncio
from pyglass.utils.argparser import parse_args
from pyglass.utils.logger import Logger
from pyglass.modules.glasses import Glasses
from pyglass.modules.packets import Packet, Text


async def main():
    clog, flog = Logger().get_loggers()
    glasses = Glasses()

    for _ in range(5):
        try:
            await glasses.scan()
        except asyncio.TimeoutError:
            clog.error("Failed to find both devices.")
            return

        if glasses.left and glasses.right:
            break

    try:
        await glasses.connect()
    except asyncio.TimeoutError:
        clog.error("Failed to connect to both devices.")
        return

    try:
        while True:
            await glasses.send_heartbeat()
            # test_message = "Hello, World! This is a test message from pyglass."
            # success = await glasses.send_text(test_message)
            # if success:
            #     clog.info(f"Message sent: {test_message}")
            # else:
            #     clog.error("Failed to send message.")
            # deadline_u32_seconds = hex(1739260938)[2:].encode()
            # test_countdown: Packet = Packet(
            #     cid=0x07,
            #     length=0x0005,
            #     seq_id=0x01,
            #     subcommand=0x01,
            #     # data=b"\x00\x00\x00\x00\x00",
            #     data=deadline_u32_seconds,
            # )
            # await glasses.send_packet(test_countdown)
            test_text: Text = Text(
                glasses._evenai_seq,
                "Hello, World! This is a test message from pyglass.",
            )
            await glasses.send_packet(test_text)
            await asyncio.sleep(8)  # for heartbeat
    except asyncio.CancelledError:
        clog.info("Received cancellation, exiting cleanly.")
    except KeyboardInterrupt:
        clog.info("KeyboardInterrupt detected, shutting down.")
    except Exception as e:
        clog.error(f"Unexpected error: {e}")
    finally:
        await glasses.disconnect()


if __name__ == "__main__":
    args = parse_args()
    Logger(verbose=args.verbose)
    asyncio.run(main())
