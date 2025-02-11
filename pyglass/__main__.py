import asyncio
from pyglass.modules.argparser import parse_args
from pyglass.modules.logger import Logger
from pyglass.modules.glasses import Glasses


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
            await asyncio.sleep(8)
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
