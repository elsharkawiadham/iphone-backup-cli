import argparse
from .doctor import run_doctor
from .setup import run_setup
from .backup import run_backup_dry_run


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

    backup_parser = subparsers.add_parser(
        "backup",
        help="Prepare an iPhone or iPad backup",
    )
    backup_parser.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="Validate without transferring any data",
    )
    backup_parser.add_argument(
        "--device",
        help="Select a connected device by its full identifier",
    )

    args = parser.parse_args()

    if args.command == "doctor":
        return run_doctor()

    if args.command == "setup":
        return run_setup()

    if args.command == "backup":
        return run_backup_dry_run(device_id=args.device)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
