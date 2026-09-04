"""Unit tests for the Robust SQL Gateway."""

import unittest
from sql_gateway import validate_sql, safe_run


class TestSQLGateway(unittest.TestCase):

    def test_valid_select_query(self):
        sql = "SELECT alt_name, address FROM core_condobuilding WHERE approved = TRUE"
        result = validate_sql(sql)
        self.assertTrue(result.ok)
        self.assertIn("LIMIT 100", result.sql)

    def test_query_with_existing_limit(self):
        sql = "SELECT alt_name FROM core_condobuilding LIMIT 10"
        result = validate_sql(sql)
        self.assertTrue(result.ok)
        self.assertIn("LIMIT 10", result.sql)

    def test_query_caps_excessive_limit(self):
        # When row_limit is not specified, it caps at default 100
        sql = "SELECT alt_name FROM core_condobuilding LIMIT 99999"
        result = validate_sql(sql)
        self.assertTrue(result.ok)
        self.assertIn("LIMIT 100", result.sql)

        # When row_limit is specified as 500, it caps at 500
        result_custom = validate_sql(sql, row_limit=500)
        self.assertTrue(result_custom.ok)
        self.assertIn("LIMIT 500", result_custom.sql)

    def test_valid_cte_query(self):
        sql = """
        WITH top_sales AS (
            SELECT condo_unit_id, sale_price FROM core_condosale WHERE sale_price > 1000000
        )
        SELECT * FROM top_sales
        """
        result = validate_sql(sql)
        self.assertTrue(result.ok)

    def test_blocks_drop_table(self):
        sql = "DROP TABLE core_condobuilding"
        result = validate_sql(sql)
        self.assertFalse(result.ok)
        self.assertTrue("Forbidden keyword detected: DROP" in result.error or "Only SELECT" in result.error)

    def test_blocks_delete_dml(self):
        sql = "DELETE FROM core_condosale WHERE id = '123'"
        result = validate_sql(sql)
        self.assertFalse(result.ok)
        self.assertTrue("Only SELECT and WITH ... SELECT queries are allowed" in result.error or "Forbidden keyword" in result.error)

    def test_blocks_insert_dml(self):
        sql = "INSERT INTO core_condomarket (name) VALUES ('Hialeah')"
        result = validate_sql(sql)
        self.assertFalse(result.ok)

    def test_blocks_update_dml(self):
        sql = "UPDATE core_condounit SET blacklist = TRUE WHERE id = 1"
        result = validate_sql(sql)
        self.assertFalse(result.ok)

    def test_blocks_select_into(self):
        sql = "SELECT * INTO stolen_table FROM core_condobuilding"
        result = validate_sql(sql)
        self.assertFalse(result.ok)
        self.assertIn("SELECT INTO", result.error)

    def test_blocks_semicolon_chaining(self):
        sql = "SELECT 1; DROP TABLE core_condobuilding;"
        result = validate_sql(sql)
        self.assertFalse(result.ok)
        self.assertIn("Multiple statements are not allowed", result.error)

    def test_blocks_dangerous_system_functions(self):
        sql = "SELECT pg_sleep(10)"
        result = validate_sql(sql)
        self.assertFalse(result.ok)
        self.assertIn("Forbidden function detected: PG_SLEEP", result.error)

    def test_safe_run_never_executes_invalid_sql(self):
        class MockDB:
            def __init__(self):
                self.executed = False

            def run(self, query):
                self.executed = True
                return "executed"

        mock_db = MockDB()
        msg, validation = safe_run(mock_db, "DROP TABLE core_condobuilding")
        self.assertFalse(validation.ok)
        self.assertFalse(mock_db.executed)
        self.assertIn("Query blocked by SQL gateway", msg)

    def test_safe_run_executes_valid_sql(self):
        class MockDB:
            def __init__(self):
                self.last_query = None

            def run(self, query):
                self.last_query = query
                return "[('Apogee', '1000 S Pointe Dr')]"

        mock_db = MockDB()
        output, validation = safe_run(mock_db, "SELECT alt_name, address FROM core_condobuilding")
        self.assertTrue(validation.ok)
        self.assertIsNotNone(mock_db.last_query)
        self.assertIn("LIMIT 100", mock_db.last_query)
        self.assertIn("Apogee", output)


if __name__ == "__main__":
    unittest.main()
