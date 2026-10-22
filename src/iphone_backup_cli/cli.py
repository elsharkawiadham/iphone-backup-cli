import argparse


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

    parser.parse_args()


if __name__ == "__main__":
    main()
