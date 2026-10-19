"""Unit tests for tool definitions, schemas, and SafeSQLQueryTool."""

import os
import unittest
from unittest.mock import patch

from tools import (
    GeocodingTool,
    GeocodingInput,
    DirectionsTool,
    DirectionsInput,
    PlacesTool,
    PlacesInput,
    ShowMapTool,
    ShowChartTool,
    SafeSQLQueryTool,
    SQLQueryInput,
    query_as_list,
)


class TestTools(unittest.TestCase):

    def test_geocoding_tool_schema(self):
        tool = GeocodingTool()
        self.assertEqual(tool.args_schema, GeocodingInput)
        valid = GeocodingInput(address="1000 Ocean Dr, Miami Beach, FL")
        self.assertEqual(valid.address, "1000 Ocean Dr, Miami Beach, FL")

        with self.assertRaises(Exception):
            GeocodingInput()  # missing address

    def test_directions_tool_schema(self):
        tool = DirectionsTool()
        self.assertEqual(tool.args_schema, DirectionsInput)
        valid = DirectionsInput(origin="1000 Collins Ave", destination="South Pointe Elementary")
        self.assertEqual(valid.origin, "1000 Collins Ave")
        self.assertEqual(valid.destination, "South Pointe Elementary")

        with self.assertRaises(Exception):
            DirectionsInput(origin="1000 Collins Ave")  # missing destination

    def test_safe_sql_tool_schema(self):
        tool = SafeSQLQueryTool()
        self.assertEqual(tool.args_schema, SQLQueryInput)
        valid = SQLQueryInput(query="SELECT * FROM core_condobuilding")
        self.assertEqual(valid.query, "SELECT * FROM core_condobuilding")

    def test_safe_sql_tool_blocks_destructive_query(self):
        class MockDB:
            def run(self, q):
                return "ok"

        tool = SafeSQLQueryTool(db=MockDB())
        result = tool.run({"query": "DROP TABLE core_condosale"})
        self.assertIn("Query blocked by SQL gateway", result)

    def test_places_tool_accepts_location_radius_and_type(self):
        tool = PlacesTool()
        self.assertEqual(tool.name, "google_places")
        self.assertEqual(tool.args_schema, PlacesInput)
        valid = PlacesInput(query="elementary school", location="25.76,-80.19", radius=5000, type="school")
        self.assertEqual(valid.location, "25.76,-80.19")
        self.assertEqual(valid.type, "school")

    def test_places_tool_missing_key_returns_error(self):
        with patch.dict(os.environ, {"GPLACES_API_KEY": ""}):
            result = PlacesTool()._run("elementary school")
        self.assertIn("GPLACES_API_KEY", result)

    def test_show_map_returns_marker_div(self):
        class FailingGeocoder:
            def geocode(self, address):
                raise RuntimeError("offline")

        html = ShowMapTool(gmaps_client=FailingGeocoder())._run(
            markers=[
                {
                    "name": "Sample Building",
                    "address": "1 Example Street",
                    "lat": 25.76,
                    "lon": -80.13,
                }
            ]
        )
        self.assertIn('id="map"', html)
        self.assertIn("data-markers=", html)
        self.assertIn("25.76", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("LATITUDE_NUMBER", html)
        self.assertNotIn("initMap", html)

    def test_show_map_uses_geocoded_address(self):
        class FakeGeocoder:
            def geocode(self, address):
                return [{"geometry": {"location": {"lat": 1.25, "lng": 2.5}}}]

        html = ShowMapTool(gmaps_client=FakeGeocoder())._run(
            markers=[{"name": "Sample", "address": "1 Example Street", "lat": 9.0, "lon": 8.0}]
        )
        self.assertIn("1.25", html)
        self.assertIn("2.5", html)
        self.assertNotIn("9.0", html)

    def test_places_limit_is_capped_at_five(self):
        class FakePlaces:
            def places(self, **kwargs):
                return {
                    "results": [
                        {
                            "name": f"Place {index}",
                            "formatted_address": f"{index} Example Street",
                            "geometry": {"location": {"lat": float(index), "lng": float(-index)}},
                        }
                        for index in range(1, 8)
                    ]
                }

        tool = PlacesTool(gmaps_client=FakePlaces())
        limited = [line for line in tool._run(query="school", limit=3).splitlines() if line.strip()]
        self.assertEqual(len(limited), 3)
        self.assertIn("lon:", limited[0])
        capped = [line for line in tool._run(query="school", limit=99).splitlines() if line.strip()]
        self.assertEqual(len(capped), 5)

    def test_show_chart_returns_canvas_without_script(self):
        html = ShowChartTool()._run(labels=["A", "B"], values=[1, 2])
        self.assertIn("<canvas", html)
        self.assertIn("data-labels=", html)
        self.assertIn("data-values=", html)
        self.assertNotIn("<script", html.lower())

    def test_query_as_list_keeps_street_numbers(self):
        class MockDB:
            def run(self, query):
                return "[('1000 Collins Avenue',), ('1 Hotel',)]"

        values = query_as_list(MockDB(), "SELECT address FROM core_condobuilding")
        self.assertIn("1000 Collins Avenue", values)
        self.assertIn("1 Hotel", values)


if __name__ == "__main__":
    unittest.main()
