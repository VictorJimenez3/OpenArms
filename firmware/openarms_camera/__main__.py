"""Command line for the station camera: list, mark, look."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from .stations import REGIONS_FILE, Camera, annotate, check_regions, load_regions, mark_station, where


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m firmware.openarms_camera")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="save one picture from each camera, to see which number is which")
    ls.add_argument("--only", type=int, nargs="+", metavar="N",
                    help="camera numbers to try (default: 0 to 4, which includes the laptop's own camera)")
    m = sub.add_parser("mark", help="teach where each station appears in the picture")
    look = sub.add_parser("look", help="report which station the object is on")
    for p in (m, look):
        p.add_argument("--camera", type=int, required=True)
        p.add_argument("--regions", type=Path, default=REGIONS_FILE)
    loc = sub.add_parser("locate", help="read the bench from a picture with the two red rulers in it")
    src = loc.add_mutually_exclusive_group(required=True)
    src.add_argument("--photo", type=Path, help="a saved picture")
    src.add_argument("--camera", type=int, help="take the picture with this webcam")
    loc.add_argument("--beaker", help="X,Y in ruler cm, to correct the detection")
    loc.add_argument("--dish", help="X,Y in ruler cm, to correct the detection")
    loc.add_argument("--apply", action="store_true", help="write the positions into the simulation's demo bench and run the pour preview")
    m.add_argument("--stations", nargs="+", default=["A", "B"])
    a = ap.parse_args()
    out = Path("outputs/camera")
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "list":
        for index in (a.only if a.only else range(5)):
            try:
                frame = Camera(index, warmup=5).read()
            except OSError:
                if a.only:
                    print(f"camera {index}: no picture (not connected, or macOS gave it a different number)")
                continue
            path = out / f"camera-{index}.jpg"
            cv2.imwrite(str(path), frame)
            print(f"camera {index}: {frame.shape[1]}x{frame.shape[0]}  saved {path}")
        print("Open the saved pictures to see which index is the bench camera.")
        return
    if a.cmd == "locate":
        locate(a, out)
        return
    camera = Camera(a.camera)
    if a.cmd == "mark":
        regions = {"camera": a.camera, "marked": time.strftime("%Y-%m-%d %H:%M"), "stations": {}}
        print("The camera must stay exactly where it is from now on.")
        for name in a.stations:
            while True:
                input(f"Put the object on station {name}, move your hands out of view, press Enter> ")
                try:
                    mark_station(regions, name, camera.read())
                    print(f"  {name}: region {regions['stations'][name]}")
                    break
                except ValueError as e:
                    print(f"  {e}. Try again.")
        for problem in check_regions(regions):
            print("PROBLEM:", problem)
        a.regions.write_text(json.dumps(regions, indent=1) + "\n")
        frame = camera.read()
        cv2.imwrite(str(out / "marked.jpg"), annotate(frame, regions, where(frame, regions)))
        print(f"Saved {a.regions}. Check the drawing in {out / 'marked.jpg'}.")
        return
    regions = load_regions(a.regions)
    if regions is None:
        raise SystemExit("No regions yet: run the mark command first.")
    frame = camera.read()
    result = where(frame, regions)
    cv2.imwrite(str(out / "look.jpg"), annotate(frame, regions, result))
    print(result["text"], f"(picture: {out / 'look.jpg'})")


def locate(a, out: Path) -> None:
    import subprocess
    import sys

    from . import bench

    image = cv2.imread(str(a.photo)) if a.photo else Camera(a.camera).read()
    if image is None:
        raise SystemExit(f"could not read {a.photo}")
    try:
        H, error = bench.ruler_mapping(image)
    except ValueError as e:
        raise SystemExit(f"Rulers: {e}")
    current = bench.read_bench()
    flat = bench.flatten(image, H)
    pieces = bench.find_pieces(flat, current["arm_cm"])
    print(f"Rulers found. Their outlines fit the 30 cm ruler shape to within {error:.1f} cm.")
    if error > 0.5:
        print("  That is a loose fit: a ruler may be partly covered, bent, or cut off by the edge of the picture.")
        print("  Positions may be a centimetre or more off; check them against the grid in the flattened picture.")
    positions = {}
    for name in ("beaker", "dish"):
        given = getattr(a, name)
        if given:
            try:
                positions[name] = tuple(float(v) for v in given.split(","))
                assert len(positions[name]) == 2
            except (ValueError, AssertionError):
                raise SystemExit(f"--{name} takes X,Y in centimetres, like --{name} 4.5,7") from None
            pieces[name] = {"cm": positions[name], "radius_cm": bench.PIECES[name]["base"], "found": "given", "note": ""}
            print(f"  {name}: {positions[name]} cm (given by you)")
        elif name in pieces:
            p = pieces[name]
            positions[name] = p["cm"]
            print(f"  {name}: {p['cm']} cm, found by its {p['found']}" + (f". Note: {p['note']}" if p["note"] else ""))
        else:
            print(f"  {name}: not found. Read it off the picture and pass --{name} X,Y")
    picture = out / "bench_flat.jpg"
    cv2.imwrite(str(picture), bench.draw(flat, pieces, current["arm_cm"]))
    print(f"Flattened picture with a 5 cm grid: {picture}  (open it and check the circles)")
    print(f"Simulation bench now has: arm base {current['arm_cm']}, beaker {current['beaker']}, dish {current['dish']}")
    if not a.apply:
        print("Nothing changed. Add --apply to put these positions into the simulation and run the pour.")
        return
    missing = [n for n in ("beaker", "dish") if n not in positions]
    if missing:
        raise SystemExit(f"Not applied: no position for the {' or the '.join(missing)}.")
    bench.write_bench(positions)
    print(f"Wrote beaker {positions['beaker']} and dish {positions['dish']} to {bench.BENCH_FILE.relative_to(bench.ROOT)}")
    solved = subprocess.run([sys.executable, "-m", "openarms_sim.ik", "--setup", "demo"], capture_output=True, text=True)
    if solved.returncode:
        raise SystemExit("Could not solve the arm poses: " + solved.stderr.strip().splitlines()[-1])
    unreachable = [line.split()[0] for line in solved.stdout.splitlines() if "cannot reach" in line]
    from openarms_sim import preview

    result = preview({"plan_id": "bench", "steps": [{"action": "add_sample", "args": {"source": "A", "into": "C", "portions": 1}}]},
                     setup="demo", use_cache=False)
    problems = [w for w in result["warnings"] if "placeholder" not in w and "joint mapping" not in w]
    if unreachable:
        problems.insert(0, f"The simulated arm cannot reach: {', '.join(unreachable)}.")
    print("\nSIMULATED POUR:", "works." if result["ok"] and not unreachable else "BLOCKED.")
    for problem in problems:
        print("  -", problem)
    if result.get("video_url"):
        print("Video:", result["video_url"].removeprefix("file://"))


if __name__ == "__main__":
    main()
