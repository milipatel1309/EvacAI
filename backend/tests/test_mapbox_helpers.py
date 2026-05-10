"""Unit tests for Mapbox nearby helpers (no live API calls)."""

import unittest

from app.services.mapbox import _bbox_around, _within_radius_km


class TestMapboxHelpers(unittest.TestCase):
    def test_bbox_contains_reference_point(self):
        lon, lat = -73.9857, 40.7484
        bbox = _bbox_around(lon, lat, 16.0)
        min_lon, min_lat, max_lon, max_lat = (float(x) for x in bbox.split(","))
        self.assertLessEqual(min_lon, lon)
        self.assertLessEqual(min_lat, lat)
        self.assertGreaterEqual(max_lon, lon)
        self.assertGreaterEqual(max_lat, lat)

    def test_within_radius(self):
        ok, d = _within_radius_km(40.7484, -73.9857, 40.7580, -73.9855, 16.0)
        self.assertTrue(ok)
        self.assertLess(d, 16.0)


if __name__ == "__main__":
    unittest.main()
