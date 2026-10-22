import argparse
from .doctor import run_doctor
from .setup import run_setup


def main():
    parser = argparse.ArgumentParser(
        prog="iphone-backup",
        description="iPhone and iPad backup manager for macOS",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="iPhone Backup CLI 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "doctor",
        help="Check system dependencies",
    )

    subparsers.add_parser("setup", help="Configure backup destinations")

    args = parser.parse_args()

    if args.command == "doctor":
        return run_doctor()

    if args.command == "setup":
        return run_setup()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
