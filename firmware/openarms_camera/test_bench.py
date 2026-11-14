"""Reading the bench from a picture: ruler mapping on a drawn scene with a known tilt, and the bench file edits."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from firmware.openarms_camera import bench

RED = (40, 40, 210)


def drawn_table(things=()):
    """A true top-down table at 20 px per cm, origin at (300, 300): two rulers in an L, plus dots at ruler cm."""
    s, o = 20, 300
    table = np.full((1300, 1200, 3), 55, np.uint8)
    L, W, a, b = bench.RULER_LENGTH, bench.RULER_WIDTH, bench.BUTT_X, bench.BUTT_Y
    px = lambda x, y: (int(round(o + x * s)), int(round(o + y * s)))  # noqa: E731
    cv2.rectangle(table, px(a, -W), px(a + L, 0), RED, -1)
    cv2.rectangle(table, px(-W, b), px(0, b + L), RED, -1)
    for x, y in things:
        cv2.circle(table, px(x, y), 6, (255, 255, 255), -1)
    return table, px


def tilted(table, lean=1.0):
    """The same table as a camera sees it leaning back: the far edge shrinks. lean=1 is a strong tilt."""
    h, w = table.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[120 * lean, 40 * lean], [w - 150 * lean, 60 * lean], [w, h], [0, h - 30 * lean]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(table, M, (w, h), borderValue=(55, 55, 55)), M


def test_ruler_mapping_recovers_table_centimetres_through_a_tilted_view():
    points = [(5, 5), (20, 4), (10, 20), (25, 25)]
    table, px = drawn_table(points)
    for lean, near, far in ((0.0, 0.2, 0.2), (0.25, 0.4, 0.6), (1.0, 0.6, 1.6)):  # straight above ... strongly tilted
        view, M = tilted(table, lean)
        H, error = bench.ruler_mapping(view)
        assert error < 0.3, (lean, error)
        seen = cv2.perspectiveTransform(np.float32([px(*p) for p in points])[None], M)[0]
        errors = [float(np.hypot(got[0] - true[0], got[1] - true[1])) for true, got in zip(points, bench.to_cm(H, seen))]
        assert max(errors[:3]) < near and errors[3] < far, (lean, errors)  # the last point is far from both rulers
    view, M = tilted(table, 0.25)
    H, _ = bench.ruler_mapping(view)
    flat = bench.flatten(view, H)
    assert flat.shape[:2] == (1000, 800)
    # In the flattened picture the dot drawn at (10, 20) cm is at its grid position.
    x, y = bench.flat_px((10, 20))
    assert flat[y - 3:y + 4, x - 3:x + 4].mean() > 150


def test_rulers_that_touch_do_not_stretch_each_others_outline():
    # Their ends overlap by 2 mm in the taped L; that sliver once added the other ruler's width to the outline.
    table, px = drawn_table()
    x = bench._ordered(bench.find_rulers(table)["x"])
    assert abs(x[0][0] - px(bench.BUTT_X, 0)[0]) <= 2 and abs(x[1][0] - px(bench.BUTT_X + bench.RULER_LENGTH, 0)[0]) <= 2


def test_missing_or_misplaced_rulers_are_explained():
    with pytest.raises(ValueError, match="red rulers"):
        bench.ruler_mapping(np.full((600, 800, 3), 55, np.uint8))
    table, _ = drawn_table()
    with pytest.raises(ValueError, match="across the top"):
        bench.ruler_mapping(cv2.rotate(table, cv2.ROTATE_180))


def test_bench_file_positions_are_read_and_rewritten_in_place(tmp_path):
    path = tmp_path / "bench.yaml"
    path.write_text(bench.BENCH_FILE.read_text())
    before = bench.read_bench(path)
    assert before["arm_cm"] == (17.0, 36.0) and before["beaker"] and before["dish"]
    bench.write_bench({"beaker": (3.2, 8.75), "dish": (21.0, 5.0)}, path)
    after = bench.read_bench(path)
    assert after["beaker"] == (3.2, 8.8) and after["dish"] == (21.0, 5.0) and after["arm_cm"] == (17.0, 36.0)
    assert path.read_text().count("\n") == bench.BENCH_FILE.read_text().count("\n")  # comments and layout kept
    assert "contents: {citric_acid: 1}" in path.read_text()


@pytest.mark.parametrize("name,dish", [("live_demo_2.jpg", (5.6, 12.8))])
def test_real_bench_photo_if_present(name, dish):
    photo = bench.ROOT / "outputs/camera" / name  # the team's own photos; not in the repository
    if not photo.exists():
        pytest.skip("bench photo not on this machine")
    image = cv2.imread(str(photo))
    H, error = bench.ruler_mapping(image)
    assert error < 0.6
    found = bench.find_pieces(bench.flatten(image, H), (17.0, 35.5))
    assert np.hypot(found["dish"]["cm"][0] - dish[0], found["dish"]["cm"][1] - dish[1]) < 1.0
