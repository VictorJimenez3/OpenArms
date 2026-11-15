"""Locate the two visible Smartivity fixture markers in a registered top-down view."""
from __future__ import annotations

from collections.abc import Mapping
import math

import numpy as np
from scipy.ndimage import label

DEFAULT_BOUNDS_M = ((.08, -.29), (.52, .29))
MARKERS = ('dock', 'receiver')


def _array(value, shape, name):
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid {name}.') from exc
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f'Invalid {name}.')
    return array


def _detect(rgb, marker, affine, expected_area, name):
    low = _array(marker.get('rgb_min'), (3,), f'{name} marker RGB minimum')
    high = _array(marker.get('rgb_max'), (3,), f'{name} marker RGB maximum')
    if np.any(low < 0) or np.any(high > 255) or np.any(low > high):
        raise ValueError(f'Invalid {name} marker RGB range.')
    offset = _array(marker.get('offset_xy_m'), (2,), f'{name} marker offset')
    mask = np.all((rgb >= low) & (rgb <= high), axis=2)
    regions, _ = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    counts = np.bincount(regions.ravel())
    candidates = np.flatnonzero(counts[1:] >= max(6, .28 * expected_area)) + 1
    if len(candidates) != 1:
        problem = 'ambiguous' if len(candidates) else 'missing or occluded'
        raise ValueError(f'The {name} fixture marker is {problem}.')
    y, x = np.nonzero(regions == candidates[0])
    width, height = np.ptp(x) + 1, np.ptp(y) + 1
    area_ratio = len(x) / expected_area
    squareness = min(width, height) / max(width, height)
    fill = len(x) / (width * height)
    if (x.min() == 0 or x.max() == rgb.shape[1] - 1 or y.min() == 0 or y.max() == rgb.shape[0] - 1
            or not .68 <= area_ratio <= 1.38 or squareness < .72 or fill < .58):
        raise ValueError(f'The {name} fixture marker is clipped, occluded, or malformed.')
    pixel = np.array([x.mean(), y.mean(), 1.])
    location = affine @ pixel - offset
    return location, {
        'pixel_xy': pixel[:2].round(3).tolist(),
        'area_px': int(len(x)),
        'expected_area_px': round(expected_area, 2),
        'fit_score': round(float(min(area_ratio, 1 / area_ratio, squareness)), 3),
    }


def locate_layout(rgb, calibration) -> dict:
    """Project marker centroids to metre coordinates using public camera calibration.

    Input is a native top-left uint8 RGB array. Calibration contains resolution,
    the marker-plane 2×3 pixel-to-world affine and each marker's RGB range and
    marker-to-fixture offset. Optional workspace bounds are [[xmin, ymin],
    [xmax, ymax]]. This estimates two fixture centers only.
    """
    if not isinstance(calibration, Mapping):
        raise ValueError('Missing camera calibration.')
    size = (calibration.get('height_px'), calibration.get('width_px'), 3)
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.shape != size:
        raise ValueError('Camera image is not native calibrated uint8 RGB.')
    affine = _array(calibration.get('pixel_to_world_xy'), (2, 3), 'marker-plane affine')
    scale = np.linalg.svd(affine[:, :2], compute_uv=False)
    if not .0001 <= scale[-1] <= scale[0] <= .01 or scale[0] / scale[-1] > 1.15:
        raise ValueError('Camera scale is incompatible with top-down marker registration.')
    pixel_area_m2 = abs(float(np.linalg.det(affine[:, :2])))
    bounds = _array(calibration.get('workspace_xy_m', DEFAULT_BOUNDS_M), (2, 2), 'workspace bounds')
    if np.any(bounds[0] >= bounds[1]):
        raise ValueError('Invalid workspace bounds.')
    markers = calibration.get('markers', {})
    locations, detections = {}, {}
    for name in MARKERS:
        marker = markers.get(name) if isinstance(markers, Mapping) else None
        if not isinstance(marker, Mapping):
            raise ValueError(f'Missing {name} marker calibration.')
        radius = float(_array(marker.get('radius_m', .006), (), f'{name} marker radius'))
        if not .003 <= radius <= .02:
            raise ValueError(f'Invalid {name} marker radius.')
        expected_area = math.pi * radius**2 / pixel_area_m2
        location, detected = _detect(rgb, marker, affine, expected_area, name)
        if np.any(location < bounds[0]) or np.any(location > bounds[1]):
            raise ValueError(f'The {name} fixture projects outside the calibrated workspace.')
        locations[name] = location
        detections[name] = detected
    if np.linalg.norm(locations['dock'] - locations['receiver']) < .08:
        raise ValueError('The two fixtures are too close for the registered operation.')
    return {
        'dock_xy': locations['dock'].tolist(),
        'receiver_xy': locations['receiver'].tolist(),
        'detections': detections,
        'confidence': min(item['fit_score'] for item in detections.values()),
        'method': 'rgb_disc_centroids_affine.v1',
        'coordinate_frame': 'mujoco_world_xy',
        'units': 'm',
        'provenance': 'SIMULATED',
    }
