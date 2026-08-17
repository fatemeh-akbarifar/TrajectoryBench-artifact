import unittest

from scripts.calculate_stability_metrics import (
    modal_proportion,
    normalize_final_answer,
    normalize_sql,
    normalized_action_sequence,
    shannon_entropy,
)


class StabilityNormalizationTest(unittest.TestCase):
    def test_normalizes_unordered_answers_and_numeric_singletons(self):
        self.assertEqual(
            normalize_final_answer("['b', 'a']", "completed", "none"),
            normalize_final_answer("['a', 'b']", "completed", "none"),
        )
        self.assertEqual(
            normalize_final_answer("['2.0']", "completed", "none"),
            normalize_final_answer("[2]", "completed", "none"),
        )

    def test_preserves_text_case_and_labels_missing_answer_by_failure(self):
        self.assertNotEqual(
            normalize_final_answer("['A']", "completed", "none"),
            normalize_final_answer("['a']", "completed", "none"),
        )
        self.assertEqual(
            normalize_final_answer("", "task limit reached", "task_limit"),
            "missing:task_limit",
        )

    def test_sql_normalization_is_quote_aware_and_preserves_order(self):
        self.assertEqual(
            normalize_sql(" SELECT   'a  b'\nFROM `T` ; "),
            "SELECT 'a  b' FROM `T`",
        )
        history = [
            {
                "role": "agent",
                "content": "Action: Operation\n```sql\nSELECT  1;\n```",
            },
            {"role": "user", "content": "[(1,)]"},
            {
                "role": "agent",
                "content": "Action: Operation\n```sql\nSELECT  2;\n```",
            },
        ]
        self.assertEqual(
            normalized_action_sequence(history, strict=False),
            ["SELECT 1", "SELECT 2"],
        )

    def test_strict_sequence_excludes_rejected_multiline_action(self):
        history = [
            {
                "role": "agent",
                "content": "Action: Operation\n```sql\nSELECT *\nFROM t;\n```",
            },
            {
                "role": "agent",
                "content": "Action: Operation\n```sql\nSELECT * FROM t;\n```",
            },
        ]
        self.assertEqual(
            normalized_action_sequence(history, strict=True), ["SELECT * FROM t"]
        )

    def test_modal_proportion_and_entropy_include_ties(self):
        values = ["a", "a", "b", "b", "c"]
        self.assertEqual(modal_proportion(values), 0.4)
        self.assertAlmostEqual(shannon_entropy(values), 1.5219280948873621)
        self.assertEqual(shannon_entropy(["a"] * 5), 0.0)


if __name__ == "__main__":
    unittest.main()
