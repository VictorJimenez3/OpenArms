"""Export and verify the OpenArms two-vessel fixture. No hardware access."""
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import cv2
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
import trimesh

ROOT = Path(__file__).resolve().parent
SCAD = ROOT / "fixture.scad"
VESSELS = ROOT.parents[2] / "simulation/models/vessels/measured_2026_11_14"
PLATE = "two-vessel-base.stl"
GAUGES = ("fit-gauge-A.stl", "fit-gauge-C.stl")
MARKER_SHEET = "aruco-markers.pdf"
DICTIONARY = "DICT_4X4_50"
MODEL_NAMES = ("donor_A", "receiver_C")


def run_scad(output, source, definitions=(), options=()):
    cmd = ["openscad", "-o", str(output), *options]
    for definition in definitions:
        cmd.extend(["-D", definition])
    result = subprocess.run([*cmd, str(source)], capture_output=True, text=True)
    if result.returncode or re.search(r"(ERROR:|WARNING:)", result.stderr) or not output.is_file():
        raise RuntimeError(result.stderr or f"OpenSCAD did not generate {output.name}")


def vessel_definitions(vessel_dir):
    vessel_data = json.loads((vessel_dir / "parameters.json").read_text())
    assert vessel_data["units"] == "mm" and vessel_data["frame"]["mesh_units"] == "m"
    assert vessel_data["frame"]["donor_spout"] == "+Y"
    donor, receiver = [vessel_data["vessels"][name] for name in MODEL_NAMES]

    def value(vessel, field):
        return vessel["dimensions"][field]["value_mm"]

    values = {
        "vessel_profiles": [donor["outer_profile"], receiver["outer_profile"]],
        "base_envelope_diameters": [value(vessel, "base_diameter") for vessel in (donor, receiver)],
        "vessel_dimensions": [
            [value(donor, "height"), value(donor, "rim_diameter_excluding_spout"),
             value(donor, "opening_diameter"), donor["spout"]["extension_mm"]],
            [value(receiver, "height"), value(receiver, "rim_diameter"),
             value(receiver, "opening_diameter"), receiver["spout"]["extension_mm"]],
        ],
        "donor_grip_band": donor["dimensions"]["grip_band_z"]["range_mm"],
    }
    return [f"{name}={json.dumps(value)}" for name, value in values.items()], vessel_data


def manifest(config, vessel_dir, vessel_data):
    deck = config["deck"]
    markers = []
    half = config["marker_edge"] / 2
    pad_z = round(deck - config["pad_recess"], 6)
    for marker_id, (x, y) in zip(config["marker_ids"], config["marker_centers"], strict=True):
        markers.append({
            "id": marker_id,
            "pad_center_mm": [x, y, pad_z],
            "black_corners_nominal_mm": [[x-half, y+half, pad_z], [x+half, y+half, pad_z],
                                         [x+half, y-half, pad_z], [x-half, y-half, pad_z]],
        })

    docks = []
    for i, (dock_id, vessel_name) in enumerate(zip("AC", MODEL_NAMES, strict=True)):
        height, rim, mouth, extension = config["vessel_dimensions"][i]
        dock = {
            "dock_id": dock_id,
            "role": "donor" if i == 0 else "receiver",
            "seat_center_mm": [*config["centers"][i], deck],
            "seat_plane_normal": [0, 0, 1],
            "seat_radius_mm": config["seat_radii"][i],
            "guide_height_mm": config["guide_heights"][i],
            "guide_outer_radius_mm": config["guide_radii"][i],
            "guide_inner_radius_by_height_mm": config["bore_profiles"][i],
            "guide_opening_center_deg_from_x": -90,
            "guide_opening_width_deg": config["guide_openings"][i],
            "nominal_radial_clearance_mm": config["radial_clearances"][i],
            "entry_chamfer_height_mm": config["chamfer_heights"][i],
            "entry_chamfer_relief_mm": config["chamfer_reliefs"][i],
            "label_center_mm": [*config["label_centers"][i], deck],
            "vessel": {
                "asset": f"{vessel_name}.stl",
                "asset_units": "m",
                "outside_height_mm": height,
                "rim_od_mm": rim,
                "opening_id_mm": mouth,
                "base_envelope_od_mm": config["base_envelope_diameters"][i],
                "outer_profile_height_radius_mm": config["vessel_profiles"][i],
                "spout_extension_mm": extension,
                "dimensions_status": vessel_data["vessels"][vessel_name]["dimensions"],
            },
        }
        if i == 0:
            dock["vessel"].update({
                "candidate_grip_height_range_mm": config["donor_grip_band"],
                "spout_azimuth_deg_from_x": config["donor_spout_deg"],
                "asset_yaw_deg": round(config["donor_spout_deg"] - 90, 6),
                "orientation_method": "manual alignment with engraved arrow toward C",
            })
        docks.append(dock)

    return {
        "schema_version": 1,
        "design_id": "openarms-two-vessel-fixture-v1",
        "units": "mm",
        "frame": {"origin": "front-left corner of fixture footprint at underside plane",
                  "x": "right", "y": "rear", "z": "up", "handedness": "right"},
        "plate": {"file": PLATE, "size_mm": [*config["platform_size"],
                                            deck + max(config["guide_heights"])],
                  "deck_thickness_mm": deck, "minimum_guide_wall_mm": config["guide_wall"],
                  "design_bed_mm": config["printer_bed"], "reserved_bed_margin_mm": config["bed_margin"],
                  "cross_tie_width_mm": config["tie_width"], "pad_rib_width_mm": config["pad_rib_width"],
                  "mount_bar_width_mm": config["mount_bar_width"]},
        "vessel_source": {"directory_name": vessel_dir.name, "revision": vessel_data["revision"],
                          "status": vessel_data["status"]},
        "docks": docks,
        "mounting": {"hole_diameter_mm": config["mount_diameter"],
                     "through_hole_centers_at_underside_mm": [[*p, 0] for p in config["mount_centers"]]},
        "fiducials": {
            "dictionary": DICTIONARY, "black_edge_mm": config["marker_edge"],
            "white_quiet_zone_per_edge_mm": config["marker_quiet"],
            "tile_size_mm": config["marker_edge"] + 2 * config["marker_quiet"],
            "pad_size_mm": config["pad_size"], "pocket_size_mm": config["paper_pocket"],
            "nominal_pad_plane_z_mm": pad_z, "artwork": MARKER_SHEET,
            "top_edge_points_toward": "+Y",
            "corner_order": ["top_left", "top_right", "bottom_right", "bottom_left"],
            "corners_status": "CAD nominal at bare pocket floor; measure after attaching labels",
            "markers": markers,
        },
        "provisional": True,
        "physical_fit_verified": False,
        "camera_detection_verified": False,
        "robot_clearance_verified": False,
        "physical_fixture_id": None,
        "calibration_id": None,
        "robot_from_fixture_transform": None,
        "mode": "taught_fixture_only",
    }


def marker_patterns(marker_ids):
    assert len(marker_ids) == len(set(marker_ids)) == 4
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    return {i: cv2.aruco.generateImageMarker(dictionary, i, 6) for i in marker_ids}


def make_artwork(path, fiducials, patterns):
    pdf = Canvas(str(path), pagesize=letter, invariant=True)
    pdf.setTitle("OpenArms fixture fiducials")
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(22*mm, 248*mm, "OpenArms fixture markers")
    pdf.setFont("Helvetica", 11)
    edge = fiducials["black_edge_mm"]
    tile = fiducials["tile_size_mm"]
    quiet = fiducials["white_quiet_zone_per_edge_mm"]
    for idx, line in enumerate([
        "Print at Actual Size / 100% on US Letter. Disable Fit to Page.",
        f"Check the 50 mm line below and a {edge:g} mm black square before cutting.",
        "Cut and attach one tile at a time. Keep each white border intact.",
        "Match the layout below. The top of every tile faces the rear of the plate (+Y).",
    ]):
        pdf.drawString(22*mm, (232-8*idx)*mm, line)
    for idx, (marker_id, pattern) in enumerate(patterns.items()):
        x, y = ((47+84*(idx % 2))*mm, (80+66*(idx // 2))*mm)
        pdf.setFont("Helvetica-Bold", 11)
        side = ("front left", "front right", "rear left", "rear right")[idx]
        pdf.drawString(x, y+(tile+5)*mm, f"{marker_id}  /  {side}")
        pdf.setDash(2, 2)
        pdf.setStrokeColorRGB(0.45, 0.45, 0.45)
        pdf.rect(x, y, tile*mm, tile*mm)
        pdf.setDash()
        module = edge*mm/6
        for row, col in np.argwhere(pattern == 0):
            pdf.rect(x+quiet*mm+col*module, y+quiet*mm+(5-row)*module,
                     module, module, stroke=0, fill=1)
    pdf.setStrokeColorRGB(0, 0, 0)
    x, y = 22*mm, 49*mm
    pdf.line(x, y, x+50*mm, y)
    for end in (x, x+50*mm):
        pdf.line(end, y-1.5*mm, end, y+1.5*mm)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(x, y+4*mm, "50 mm print scale")
    pdf.drawString(x, 35*mm, f"{DICTIONARY}  /  {edge:g} mm black edge  /  {tile:g} mm cut tile")
    pdf.showPage()
    pdf.save()


def load_solid(path, expected_size):
    mesh = trimesh.load_mesh(path, process=True)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0, path.name
    assert len(mesh.split(only_watertight=False)) == 1, path.name
    assert np.allclose(mesh.bounds[0], 0, atol=0.002), path.name
    assert np.allclose(mesh.extents, expected_size, atol=0.002), (path.name, mesh.extents)
    assert np.any(mesh.face_normals[:, 2] < -0.999), path.name
    return mesh


def vertical_hit(mesh, xy):
    hits, _, _ = mesh.ray.intersects_location([[*xy, 100]], [[0, 0, -1]])
    return max(hits[:, 2]) if len(hits) else None


def check_dock(mesh, dock, center, floor_z, vessel_dir):
    radii = np.array(dock["guide_inner_radius_by_height_mm"])
    height = dock["guide_height_mm"]
    outer = dock["guide_outer_radius_mm"]
    for z in sorted({0.1, height-0.1, *radii[1:-1, 0]}):
        origin = [*center, floor_z+z]
        expected_inner = np.interp(z, radii[:, 0], radii[:, 1])
        for direction in ([0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, -1, 0]):
            points, _, _ = mesh.ray.intersects_location([origin], [direction])
            distances = np.sort(np.linalg.norm(points.reshape(-1, 3)-np.array(origin), axis=1))
            nearby = distances[distances <= outer+0.02]
            if direction == [0, -1, 0]:
                assert not len(nearby), dock["dock_id"]
            else:
                assert np.allclose(nearby, [expected_inner, outer], atol=0.02), (dock["dock_id"], nearby)
    vessel = trimesh.load_mesh(vessel_dir / dock["vessel"]["asset"])
    mesh_height = vessel.extents[2] * 1000
    assert np.isclose(mesh_height, dock["vessel"]["outside_height_mm"], atol=0.02)
    vertices = vessel.vertices * 1000
    assert abs(vertices[:, 2].min()) < 0.01
    lower_vertices = vertices[vertices[:, 2] <= height]
    free_space = (np.interp(lower_vertices[:, 2], radii[:, 0], radii[:, 1])
                  - np.linalg.norm(lower_vertices[:, :2], axis=1))
    # Both the measured mesh and the fixture bore are piecewise-linear in height.
    # Check vessel vertices plus bore breakpoints, where the minimum can also occur.
    outer_profile = np.array(dock["vessel"]["outer_profile_height_radius_mm"])
    profile_clearance = radii[:, 1] - np.interp(radii[:, 0], outer_profile[:, 0], outer_profile[:, 1])
    minimum = float(min(free_space.min(), profile_clearance.min()))
    assert minimum >= dock["nominal_radial_clearance_mm"] - 0.02
    probe_radius = dock["vessel"]["base_envelope_od_mm"] / 4
    for offset in ([0, 0], [probe_radius, 0], [0, probe_radius], [-probe_radius, 0], [0, -probe_radius]):
        assert np.isclose(vertical_hit(mesh, np.array(center)+offset), floor_z, atol=0.002)
    return round(minimum, 3)


def verify(out, cfg, reference, vessel_dir, patterns):
    plate = load_solid(out / PLATE, reference["plate"]["size_mm"])
    meshes = {PLATE: plate}
    model_clearance = {}
    for i, (dock, gauge_file) in enumerate(zip(reference["docks"], GAUGES, strict=True)):
        r = dock["seat_radius_mm"]
        gauge = load_solid(out / gauge_file, [2*r, 2*r, cfg["gauge_floor"]+dock["guide_height_mm"]])
        meshes[gauge_file] = gauge
        model_clearance[dock["dock_id"]] = check_dock(plate, dock, cfg["centers"][i], cfg["deck"], vessel_dir)
        check_dock(gauge, dock, [r, r], cfg["gauge_floor"], vessel_dir)

    tags = reference["fiducials"]
    for marker in tags["markers"]:
        x, y, z = marker["pad_center_mm"]
        half_tile = tags["tile_size_mm"]/2
        for dx, dy in [(0, 0), (-half_tile, -half_tile), (-half_tile, half_tile),
                       (half_tile, -half_tile), (half_tile, half_tile)]:
            assert np.isclose(vertical_hit(plate, (x+dx, y+dy)), z, atol=0.002)
        for point in marker["black_corners_nominal_mm"]:
            assert np.isclose(vertical_hit(plate, point[:2]), z, atol=0.002)
        for sign in (-1, 1):
            assert np.isclose(vertical_hit(plate, (x+sign*(tags["pocket_size_mm"]/2+0.4), y)),
                              cfg["deck"], atol=0.002)
    for x, y in cfg["mount_centers"]:
        assert vertical_hit(plate, (x, y)) is None
        for sign in (-1, 1):
            assert vertical_hit(plate, (x+sign*(cfg["mount_diameter"]/2-0.1), y)) is None
            assert np.isclose(vertical_hit(plate, (x+sign*(cfg["mount_diameter"]/2+0.1), y)),
                              cfg["deck"], atol=0.002)

    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    detector = cv2.aruco.ArucoDetector(dictionary)
    for marker_id, pattern in patterns.items():
        raster = np.pad(pattern, 1, constant_values=255).repeat(24, axis=0).repeat(24, axis=1)
        for turn in range(4):
            _, ids, _ = detector.detectMarkers(np.rot90(raster, turn).copy())
            assert ids is not None and ids.ravel().tolist() == [marker_id]
    return {
        "meshes": {name: {"watertight": True, "consistent_winding": True, "connected_solids": 1,
                          "extents_mm": np.round(mesh.extents, 3).tolist(),
                          "geometric_volume_cm3": round(mesh.volume/1000, 3)}
                   for name, mesh in meshes.items()},
        "geometry": {
            "two_seats_with_matching_gauges": "passed",
            "minimum_model_radial_clearance_mm": model_clearance,
            "guide_wall_and_open_front": "passed section probes",
            "marker_pad_floor_and_reference_corners": "passed",
            "mount_through_holes": "passed",
            "configured_bed_fit": "passed for configured envelope only",
            "marker_source_patterns_decode_all_quarter_turns": list(patterns),
        },
        "physical_qualification": {
            "vessel_fit": "unverified",
            "marker_print_scale_and_camera_readability": "unverified",
            "robot_clearance_and_pour": "unverified",
            "slicer": "not run",
        },
    }


def render_preview(path, plate, reference, vessel_dir, patterns, scratch):
    scene = [f"color([0.28,0.33,0.38]) import({json.dumps(str(plate))});"]
    for i, dock in enumerate(reference["docks"]):
        vessel = dock["vessel"]
        mesh = json.dumps(str(vessel_dir / vessel["asset"]))
        angle = vessel.get("asset_yaw_deg", 0)
        color = ([0.23, 0.62, 0.79, 0.69], [0.37, 0.77, 0.66, 0.72])[i]
        x, y, z = dock["seat_center_mm"]
        scene.append(f"color({color}) translate([{x},{y},{z+0.03}]) rotate([0,0,{angle}]) "
                     f"scale([1000,1000,1000]) import({mesh});")
    tags = reference["fiducials"]
    tile = tags["tile_size_mm"]
    edge = tags["black_edge_mm"]
    for marker in tags["markers"]:
        x, y, z = marker["pad_center_mm"]
        scene.append(f"color([1,1,1]) translate([{x-tile/2},{y-tile/2},{z}]) "
                     f"cube([{tile},{tile},0.12]);")
        for row, col in np.argwhere(patterns[marker["id"]] == 0):
            offset_x = x-edge/2+col*edge/6
            offset_y = y-edge/2+(5-row)*edge/6
            scene.append(f"color([0.035,0.035,0.035]) translate([{offset_x},{offset_y},{z+0.12}]) "
                         f"cube([{edge/6},{edge/6},0.03]);")
    x, y, _ = reference["docks"][0]["label_center_mm"]
    scene.append(f"color([0.12,0.45,0.64]) translate([{x},{y-17},4.1]) linear_extrude(0.2) "
                 "polygon([[-1,0],[1,0],[1,9],[3,9],[0,13],[-3,9],[-1,9]]);")
    preview = scratch / "assembly.scad"
    preview.write_text("\n".join(scene))
    run_scad(path, preview, options=["--imgsize=1440,1040", "--viewall", "--autocenter",
                                     "--projection=o", "--colorscheme=Tomorrow",
                                     "--camera=0,0,0,16,0,10,340"])


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "exports")
    parser.add_argument("--vessel-dir", type=Path, default=VESSELS,
                        help="Directory with the vessel parameters and matching metre-scale STL meshes")
    args = parser.parse_args()
    out = args.out.resolve()
    vessel_dir = args.vessel_dir.resolve()
    definitions, vessel_data = vessel_definitions(vessel_dir)
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        echo = scratch / "fixture.echo"
        run_scad(echo, SCAD, [*definitions, 'part="config"'])
        config = dict(json.loads(echo.read_text().strip().removeprefix("ECHO: ")))
        reference = manifest(config, vessel_dir, vessel_data)
        jobs = [(PLATE, ['part="platform"'])]
        jobs += [(name, ['part="gauge"', f"gauge_index={i}"]) for i, name in enumerate(GAUGES)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(
                lambda job: run_scad(scratch / job[0], SCAD, [*definitions, *job[1]],
                                     options=["--export-format", "binstl"]),
                jobs,
            ))
        patterns = marker_patterns(config["marker_ids"])
        report = verify(scratch, config, reference, vessel_dir, patterns)
        render_preview(scratch / "two-vessel-preview.png", scratch / PLATE,
                       reference, vessel_dir, patterns, scratch)
        make_artwork(scratch / MARKER_SHEET, reference["fiducials"], patterns)
        write_json(scratch / "fixture-reference.json", reference)
        write_json(scratch / "validation.json", report)
        for name in [PLATE, *GAUGES, "two-vessel-preview.png", MARKER_SHEET,
                     "fixture-reference.json", "validation.json"]:
            (out / name).write_bytes((scratch / name).read_bytes())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
