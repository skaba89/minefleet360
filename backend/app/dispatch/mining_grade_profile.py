"""Directional grades from qualified survey samples, not GPS altitude estimates."""

from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class SurveyPoint:
    horizontal_chainage_mm: int
    elevation_mm: int


@dataclass(frozen=True)
class DirectionalGrades:
    uphill_permille: int
    downhill_permille: int


def surveyed_grades(points: list[SurveyPoint]) -> DirectionalGrades | None:
    """Return maximum sampled grades rounded upwards, or None for invalid input.

    Chainage is cumulative horizontal distance in travel direction, not 3D
    path length. Survey completeness, sampling resolution and measurement
    uncertainty must be independently qualified before operational use.
    """
    if not 2 <= len(points) <= 10000:
        return None
    if points[0].horizontal_chainage_mm != 0:
        return None
    uphill = downhill = 0
    for previous, current in pairwise(points):
        distance = current.horizontal_chainage_mm - previous.horizontal_chainage_mm
        if distance <= 0:
            return None
        rise = current.elevation_mm - previous.elevation_mm
        magnitude = (abs(rise) * 1000 + distance - 1) // distance
        if rise > 0:
            uphill = max(uphill, magnitude)
        elif rise < 0:
            downhill = max(downhill, magnitude)
    return DirectionalGrades(uphill, downhill)
