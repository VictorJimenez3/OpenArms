"""The station check on the real bench photos in the repo, and on drawn pictures."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from firmware.openarms_camera.stations import annotate, check_regions, find_objects, mark_station, region_around, where

PHOTOS = Path(__file__).resolve().parents[2] / "research/joseph/mandarin-transfer-2026-11-14/images"


def photo(name):
    image = cv2.imread(str(PHOTOS / name))
    if image is None:
        pytest.skip("bench photos are not in this checkout")
    return image


def drawn(spots, size=(480, 640)):
    image = np.full((*size, 3), 40, np.uint8)
    cv2.rectangle(image, (0, 400), (640, 480), (40, 40, 200), -1)  # a red card: must not count
    for x, y in spots:
        cv2.circle(image, (x, y), 30, (20, 120, 240), -1)  # orange in BGR
    return image


@pytest.mark.parametrize("name", ["before-camera-0.jpg", "before-camera-1.jpg", "after-camera-0.jpg", "after-camera-1.jpg",
                                  "carry-camera-0.jpg", "carry-camera-1.jpg", "raised-check-camera-0.jpg", "raised-check-camera-1.jpg"])
def test_finds_exactly_one_object_in_every_real_bench_photo(name):
    found = find_objects(photo(name))
    assert len(found) == 1, found  # one mandarin; the red card and the jaw are not objects


def test_real_photos_from_the_side_camera_tell_pickup_from_b_and_from_the_air():
    before, after = photo("before-camera-0.jpg"), photo("after-camera-0.jpg")
    regions = mark_station(mark_station({}, "C", before), "B", after)
    assert check_regions(regions) == []
    assert where(before, regions)["station"] == "C"
    assert where(after, regions)["station"] == "B"
    carried = where(photo("carry-camera-0.jpg"), regions)
    assert carried["seen"] and carried["station"] is None and carried["status"] == "elsewhere"


def test_a_table_level_view_along_the_stations_is_reported_as_unusable():
    # Camera 1 looks along the line from the pickup to B: both land on the same spot in its picture.
    regions = mark_station(mark_station({}, "C", photo("before-camera-1.jpg")), "B", photo("after-camera-1.jpg"))
    assert "same place" in check_regions(regions)[0]


def test_drawn_scene_states():
    regions = mark_station(mark_station({}, "A", drawn([(150, 250)])), "B", drawn([(450, 250)]))
    assert where(drawn([(155, 255)]), regions)["station"] == "A"
    assert where(drawn([(445, 245)]), regions)["station"] == "B"
    assert where(drawn([(300, 80)]), regions)["status"] == "elsewhere"
    assert where(drawn([]), regions) == {"station": None, "seen": False, "status": "not_seen", "objects": [],
                                          "text": "The camera does not see the object."}
    assert where(drawn([(150, 250), (450, 250)]), regions)["status"] == "unclear"
    assert annotate(drawn([(150, 250)]), regions, where(drawn([(150, 250)]), regions)).shape == (480, 640, 3)


def test_a_moved_camera_or_overlapping_stations_are_reported():
    regions = mark_station(mark_station({}, "A", drawn([(150, 250)])), "B", drawn([(170, 250)]))
    assert "same place" in check_regions(regions)[0]
    with pytest.raises(ValueError, match="marked at"):
        where(drawn([(150, 250)], size=(240, 320)), regions)
    with pytest.raises(ValueError, match="no orange object"):
        mark_station({}, "A", drawn([]))
    assert region_around((10, 10, 20, 20), (100, 100, 3)) == [0, 0, 42, 42]


def test_a_long_orange_strip_like_a_wooden_desk_edge_is_not_the_object():
    image = drawn([(300, 250)])
    cv2.rectangle(image, (0, 100), (400, 130), (20, 120, 240), -1)  # same colour as the fruit, wrong shape
    found = find_objects(image)
    assert len(found) == 1 and abs(found[0]["center"][0] - 300) < 5


def test_a_picture_that_is_mostly_orange_has_no_object():
    assert find_objects(np.full((480, 640, 3), (20, 120, 240), np.uint8)) == []
