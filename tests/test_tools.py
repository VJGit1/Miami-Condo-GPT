"""Unit tests for tool definitions, schemas, and SafeSQLQueryTool."""

import unittest
from tools import (
    GeocodingTool,
    GeocodingInput,
    DirectionsTool,
    DirectionsInput,
    SafeSQLQueryTool,
    SQLQueryInput,
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


if __name__ == "__main__":
    unittest.main()
