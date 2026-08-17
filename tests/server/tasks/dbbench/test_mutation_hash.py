import unittest

from src.server.tasks.dbbench import mutation_table_hash


class DBBenchMutationHashTest(unittest.TestCase):
    def test_matches_historical_nested_md5_algorithm(self):
        rows = [("a", "b"), ("c", None)]
        self.assertEqual(
            mutation_table_hash(rows), "735a884f6654b59bf5392f2135e1065d"
        )

    def test_row_order_does_not_change_hash(self):
        rows = [("a", "b"), ("c", "d")]
        self.assertEqual(mutation_table_hash(rows), mutation_table_hash(reversed(rows)))


if __name__ == "__main__":
    unittest.main()
