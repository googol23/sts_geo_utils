"""Command-line entry point for ROOT geometry inspection utilities."""

import argparse
import sys
from importlib import import_module

from . import __version__

COMMANDS = {
    "extract": (
        "extraction",
        "Export sensor centres, local sizes and orientations using external ROOT",
    ),
    "bounds": (
        "extract_sensors",
        "Export global axis-aligned sensor bounds using PyROOT",
    ),
    "ladder": (
        "ladder",
        "Export one ladder's sensor boxes as JSON using external ROOT",
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, (_, description) in COMMANDS.items():
        subparsers.add_parser(name, help=description, add_help=False)
    args, remaining = parser.parse_known_args(argv)
    try:
        module = import_module(f".{COMMANDS[args.command][0]}", __package__)
        return module.main(remaining)
    except ModuleNotFoundError as error:
        if error.name != "ROOT":
            raise
        print(
            "geo-inspector: configure a PyROOT environment to use bounds; "
            "extract uses external ROOT instead",
            file=sys.stderr,
        )
        return 1
