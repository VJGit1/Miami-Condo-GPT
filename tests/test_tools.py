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

    def test_query_as_list_keeps_street_numbers(self):
        class MockDB:
            def run(self, query):
                return "[('1000 Collins Avenue',), ('1 Hotel',)]"

        values = query_as_list(MockDB(), "SELECT address FROM core_condobuilding")
        self.assertIn("1000 Collins Avenue", values)
        self.assertIn("1 Hotel", values)


if __name__ == "__main__":
    unittest.main()
