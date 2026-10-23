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
        help="Validate without transferring any data",
    )
    backup_parser.add_argument(
        "--device",
        help="Select a connected device by its full identifier",
    )

    simulation_parser = subparsers.add_parser(
        "simulate", help="Run a disposable mock writer; no device communication",
    )
    simulation_parser.add_argument(
        "--sandbox", action="store_true",
        help="Run mock writer inside the macOS filesystem sandbox",
    )
    simulation_parser.add_argument("--destination", required=True,
                                   help="Existing dedicated directory on an external volume")
    simulation_parser.add_argument("--scenario", choices=("success", "failure", "timeout"),
                                   default="success")
    status_parser = subparsers.add_parser("simulation-status", help="Read a preserved simulation journal")
    status_parser.add_argument("operation")

    args = parser.parse_args()

    if args.command == "doctor":
        return run_doctor()

    if args.command == "setup":
        return run_setup()

    if args.command == "backup":
        if not args.dry_run:
            print("[SAFE] Real backup execution is disabled. Use backup --dry-run.")
            return 3
        return run_backup_dry_run(device_id=args.device)

    if args.command in {"simulate", "simulation-status"}:
        from .controlled_execution import run_controlled_simulation, read_simulation_status
        from .storage import identify_volume, StorageUnavailableError
        try:
            if args.command == "simulate":
                volume = identify_volume(args.destination, require_external=True)
                result = run_controlled_simulation(
                    args.destination, volume["mount_point"], volume["volume_uuid"],
                    scenario=args.scenario,
                    **({'sandboxed': True} if args.sandbox else {}),
                )
            else:
                result = read_simulation_status(args.operation)
        except KeyboardInterrupt:
            print("[SIMULATION] interrupted")
            return 130
        except (OSError, ValueError, StorageUnavailableError) as error:
            print(f"[SIMULATION] unavailable: {error}")
            return 5
        print(f"[SIMULATION] {result.status}")
        if result.operation:
            print(f"Operation: {result.operation}")
        if result.detail:
            print(result.detail)
        if not result.journal_recorded and result.operation:
            print("No terminal journal confirmed; output is preserved. Do not resume automatically.")
        return result.exit_code

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
