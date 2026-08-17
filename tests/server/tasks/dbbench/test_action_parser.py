import unittest

from src.server.tasks.dbbench.action_parser import (
    build_repair_prompt,
    parse_dbbench_action,
)


class DBBenchActionParserTest(unittest.TestCase):
    def test_parses_operation(self):
        result = parse_dbbench_action(
            "Reasoning\nAction: Operation\n```sql\nSELECT 1;\n```",
            strict=True,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.action.kind, "operation")
        self.assertEqual(result.action.sql, "SELECT 1;")

    def test_strict_mode_requires_action_answer(self):
        result = parse_dbbench_action(
            'Reasoning\nFinal Answer: ["value"]', strict=True
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.error, "missing_action")

    def test_baseline_mode_preserves_legacy_final_answer_behavior(self):
        result = parse_dbbench_action(
            'Reasoning\nFinal Answer: ["value"]', strict=False
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.action.kind, "answer")

    def test_strict_mode_rejects_multiline_sql(self):
        result = parse_dbbench_action(
            "Action: Operation\n```sql\nSELECT *\nFROM table_name;\n```",
            strict=True,
        )

        self.assertFalse(result.valid)
        self.assertEqual(result.error, "sql_must_be_one_line")

    def test_repair_prompt_contains_reason_and_both_formats(self):
        prompt = build_repair_prompt("missing_action")

        self.assertIn("missing_action", prompt)
        self.assertIn("Action: Operation", prompt)
        self.assertIn("Action: Answer", prompt)


if __name__ == "__main__":
    unittest.main()
