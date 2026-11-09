"""Isolation and CLI regressions; no external ROOT installation is needed."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from geo_inspector.cli import main
from geo_inspector.extraction import extract_geometry

PACKAGE = Path(__file__).resolve().parents[1]


def test_standalone_copy_with_declared_dependencies(tmp_path):
    shutil.copytree(
        PACKAGE,
        tmp_path / "geo_inspector",
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "build", "*.egg-info", "__pycache__", ".pytest_cache"
        ),
    )
    code = """
import sys
from pathlib import Path
import importlib.util
import geo_inspector
from geo_inspector.sts import build_module_name_prefix
from sts_utils.sts_naming import build_module_name_prefix as shared_prefix
assert Path(geo_inspector.__file__).resolve().parent == Path.cwd() / 'geo_inspector'
assert build_module_name_prefix is shared_prefix
assert build_module_name_prefix(3, 'D', 'R', 1, 'T', 0) == 'M4DR1T0'
assert not {'ROOT', 'CameraView', 'utils', 'module_grades', 'matplotlib', 'pandas', 'vtk', 'numpy'} & sys.modules.keys()
for name in ('naming', 'inspect_sts_geometry', 'plot_module_grades', 'inspect_module_table'):
    assert importlib.util.find_spec('geo_inspector.' + name) is None
"""
    subprocess.run([sys.executable, "-c", code], cwd=tmp_path, check=True, timeout=30)
    for command in ([], ["extract"], ["bounds"], ["ladder"]):
        result = subprocess.run(
            [sys.executable, "-m", "geo_inspector", *command, "--help"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout


def test_extraction_macro_is_bundled():
    assert (PACKAGE / "extract_sts_sensors.C").is_file()


def test_extract_cli_uses_working_directory(tmp_path, monkeypatch):
    import geo_inspector.extraction as extraction

    source = tmp_path / "geometry.root"
    source.touch()

    def extract(geometry, output, root):
        assert geometry == source
        output.write_text("geometry-only CSV")

    monkeypatch.setattr(extraction, "extract_geometry", extract)
    monkeypatch.chdir(tmp_path)
    assert main(["extract", str(source)]) == 0
    assert (tmp_path / "data/output/sensors.csv").read_text() == "geometry-only CSV"


def test_external_root_wrapper_and_cleanup(tmp_path, monkeypatch):
    import geo_inspector.extraction as extraction

    geometry = tmp_path / "geometry with spaces.root"
    geometry.touch()
    output = tmp_path / "sensors.csv"
    monkeypatch.setattr(extraction.shutil, "which", lambda root: "/configured/root")
    wrappers = []

    def run(command, check, stdout):
        assert stdout is None
        assert command[:4] == ["/configured/root", "-l", "-b", "-q"]
        assert check
        wrapper = Path(command[4])
        wrappers.append(wrapper)
        content = wrapper.read_text()
        assert json.dumps(geometry.as_posix()) in content
        assert json.dumps(output.as_posix()) in content
        assert "extract_sts_sensors.C" in content

    monkeypatch.setattr(extraction.subprocess, "run", run)
    extract_geometry(geometry, output)
    assert not wrappers[0].exists()


def test_wrapper_requests_optional_node_transforms(tmp_path, monkeypatch):
    import geo_inspector.extraction as extraction

    geometry = tmp_path / "geometry.root"
    geometry.touch()
    output = tmp_path / "sensors.csv"
    nodes = tmp_path / "node transforms.csv"
    monkeypatch.setattr(extraction.shutil, "which", lambda root: "/configured/root")

    def run(command, check, stdout):
        wrapper = Path(command[4]).read_text()
        assert (
            f"{json.dumps(output.as_posix())}, {json.dumps(nodes.as_posix())}"
            in wrapper
        )
        assert check

    monkeypatch.setattr(extraction.subprocess, "run", run)
    extract_geometry(geometry, output, node_transforms=nodes)


@pytest.mark.parametrize("target", ["geometry.root", "sensors.csv"])
def test_node_transform_output_cannot_overwrite_input_or_sensor_csv(tmp_path, target):
    geometry = tmp_path / "geometry.root"
    geometry.write_bytes(b"geometry")
    output = tmp_path / "sensors.csv"
    output.write_bytes(b"existing CSV")
    with pytest.raises(ValueError, match="must differ"):
        extract_geometry(geometry, output, node_transforms=tmp_path / target)
    assert geometry.read_bytes() == b"geometry"
    assert output.read_bytes() == b"existing CSV"


def test_extraction_rejects_input_overwrite(tmp_path):
    source = tmp_path / "geometry.root"
    source.write_bytes(b"unchanged")
    with pytest.raises(ValueError, match="differ"):
        extract_geometry(source, source)
    assert source.read_bytes() == b"unchanged"


def test_missing_root_is_actionable(tmp_path, monkeypatch):
    import geo_inspector.extraction as extraction

    source = tmp_path / "geometry.root"
    source.touch()
    monkeypatch.setattr(extraction.shutil, "which", lambda root: None)
    with pytest.raises(ValueError, match="ROOT executable not found"):
        extract_geometry(source, tmp_path / "output.csv")
