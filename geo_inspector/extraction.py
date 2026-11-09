"""Extract full local sensor dimensions and placements using external ROOT."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .paths import OUTPUT_DIR
else:
    from paths import OUTPUT_DIR


def extract_geometry(
    geometry, output, root="root", *, stdout=None, node_transforms=None
):
    """Run the bundled macro; explicit paths are relative to the working directory.

    The caller owns output-directory creation. ROOT is inherited from the
    externally configured environment; no FairRoot or Python ROOT is imported.
    ``stdout`` optionally redirects ROOT's console output to an open stream.
    ``node_transforms`` optionally names a second CSV of node-to-global poses,
    using each node's origin (not its shape's bounding-box origin).
    """
    geometry, output = Path(geometry).resolve(), Path(output).resolve()
    if geometry == output:
        raise ValueError("Output must differ from the geometry input")
    if node_transforms is not None:
        node_transforms = Path(node_transforms).resolve()
        if node_transforms in (geometry, output):
            raise ValueError(
                "Node transforms output must differ from geometry input and sensor output"
            )
    if not geometry.is_file():
        raise ValueError(f"Geometry file does not exist: {geometry}")
    executable = shutil.which(root)
    if executable is None:
        raise ValueError(
            "ROOT executable not found; set up your ROOT environment first or use --root"
        )
    macro = Path(__file__).with_name("extract_sts_sensors.C").resolve()
    with tempfile.TemporaryDirectory(prefix="geo-inspector-") as directory:
        wrapper = Path(directory) / "run_extract.C"
        node_argument = (
            f", {json.dumps(node_transforms.as_posix())}"
            if node_transforms is not None
            else ""
        )
        wrapper.write_text(
            f"#include {json.dumps(macro.as_posix())}\n"
            "void run_extract() { extract_sts_sensors("
            f"{json.dumps(geometry.as_posix())}, {json.dumps(output.as_posix())}{node_argument}"
            "); }\n",
            encoding="utf-8",
        )
        subprocess.run(
            [executable, "-l", "-b", "-q", str(wrapper)], check=True, stdout=stdout
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path, help="Input ROOT geometry file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("sensors.csv"),
        help="Filename under ./data/output, or an absolute path",
    )
    parser.add_argument(
        "--root", default="root", help="Externally configured ROOT executable"
    )
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else OUTPUT_DIR / args.output
    try:
        # Check before creating directories or asking ROOT to write anything.
        if output.resolve() == args.geometry.resolve():
            raise ValueError("Output must differ from the geometry input")
        output.parent.mkdir(parents=True, exist_ok=True)
        extract_geometry(args.geometry, output, args.root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"geo-inspector extract: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
