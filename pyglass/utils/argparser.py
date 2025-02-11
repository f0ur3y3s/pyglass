import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PyGlass")

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()
