"""Real ROOT coordinate checks, when ROOT is configured externally."""

import csv
import shutil
import subprocess
from pathlib import Path

import pytest
from geo_inspector import load_ladder_geometries, load_ladder_geometry
from geo_inspector.sts import ROTATION_FIELDS

HERE = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    shutil.which("root") is None, reason="External ROOT environment is not set"
)
def test_root_transform_and_export_formats(tmp_path):
    # Real ROOT fixture: nonzero shape origin, nested translation and 90 degree rotation.
    fixture = tmp_path / "fixture.C"
    fixture.write_text("""
#include <TGeoManager.h>
#include <TGeoVolume.h>
#include <TGeoMatrix.h>
#include <TGeoBBox.h>
#include <TFile.h>
void fixture() {
    auto* geo = new TGeoManager("fixture", "fixture");
    auto* top = new TGeoVolumeAssembly("TOP");
    auto* sts = new TGeoVolumeAssembly("sts");
    auto* unit = new TGeoVolumeAssembly("Unit00R");
    auto* ladder = new TGeoVolumeAssembly("LadderType0010");
    auto* half = new TGeoVolumeAssembly("HalfLadder10t");
    auto* module = new TGeoVolumeAssembly("HalfLadder10t_Module01");
    double origin[3] = {1, 2, 3};
    auto* sensor = new TGeoVolume("Sensor01", new TGeoBBox("box", 3.1, 1.1, .015, origin));
    geo->SetTopVolume(top);
    top->AddNode(sts, 1, new TGeoTranslation(0, 0, 59.5));
    auto* unitRotation = new TGeoRotation(); unitRotation->RotateZ(90);
    sts->AddNode(unit, 1, new TGeoCombiTrans(10, 20, 30, unitRotation));
    auto* rotation = new TGeoRotation(); rotation->RotateZ(90);
    unit->AddNode(ladder, 101, new TGeoCombiTrans(0, 0, 0, rotation));
    ladder->AddNode(half, 1);
    half->AddNode(module, 1, new TGeoTranslation(4, 5, 6));
    module->AddNode(sensor, 1);
    geo->CloseGeometry();
    { TFile file("manager.root", "RECREATE"); geo->Write(); }
    sts->Export("volume.root");
    { TFile file("volume.root", "UPDATE"); TGeoTranslation placement("sts_trans",0,0,59.5); placement.Write(); }
}
""")
    subprocess.run(["root", "-l", "-b", "-q", str(fixture)], cwd=tmp_path, check=True)
    macro = (HERE / "extract_sts_sensors.C").resolve()
    results = []
    for kind in ("manager", "volume"):
        subprocess.run(
            [
                "root",
                "-l",
                "-b",
                "-q",
                f'{macro}("{kind}.root","{tmp_path / (kind + ".csv")}","{tmp_path / (kind + "_nodes.csv")}")',
            ],
            cwd=tmp_path,
            check=True,
        )
        with (tmp_path / f"{kind}.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1
        row = rows[0]
        assert [
            float(row[key]) for key in ("x", "y", "z", "dx", "dy", "dz")
        ] == pytest.approx([5, 13, 98.5, 6.2, 2.2, 0.03])
        ladder = load_ladder_geometry(tmp_path / f"{kind}.csv", "LadderType0010_101")
        sensor = ladder.sensors[0]
        assert sensor.center == pytest.approx((5, 13, 98.5))
        assert sensor.dimensions == pytest.approx((6.2, 2.2, 0.03))
        assert sensor.bounds.minimum == pytest.approx((1.9, 11.9, 98.485))
        assert sensor.bounds.maximum == pytest.approx((8.1, 14.1, 98.515))
        assert ladder.bounds == sensor.bounds
        (local,) = load_ladder_geometries(
            tmp_path / f"{kind}.csv",
            "Unit00R_1",
            node_transforms=tmp_path / f"{kind}_nodes.csv",
        )
        assert local.sensors[0].center == pytest.approx((-7, 5, 9))
        assert local.bounds.minimum == pytest.approx((-8.1, 1.9, 8.985))
        assert local.bounds.maximum == pytest.approx((-5.9, 8.1, 9.015))
        assert local.reference_frame.translation == pytest.approx((10, 20, 89.5))
        assert local.reference_frame.rotation[0] == pytest.approx((0, -1, 0))
        assert local.reference_frame.rotation[1] == pytest.approx((1, 0, 0))
        assert local.to_dict()["schema_version"] == 2
        results.append([float(row[key]) for key in ROTATION_FIELDS])
    assert results[0] == pytest.approx(results[1])
