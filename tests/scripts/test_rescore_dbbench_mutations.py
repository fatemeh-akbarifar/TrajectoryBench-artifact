import unittest

from scripts.rescore_dbbench_mutations import executed_sql


class MutationReplayTest(unittest.TestCase):
    def test_replays_only_parser_accepted_actions_in_order(self):
        history = [
            {"role": "agent", "content": "invalid"},
            {
                "role": "agent",
                "content": "Action: Operation\n```sql\nUPDATE t SET x=1;\n```",
            },
            {"role": "user", "content": "[]"},
            {"role": "agent", "content": "Action: Answer\nFinal Answer: done"},
            {
                "role": "agent",
                "content": "Action: Operation\n```sql\nUPDATE t SET x=2;\n```",
            },
        ]
        self.assertEqual(
            executed_sql(history, strict=True, max_round=10),
            ["UPDATE t SET x=1;"],
        )

    def test_does_not_replay_operation_observed_after_round_limit(self):
        history = [
            {
                "role": "agent",
                "content": f"Action: Operation\n```sql\nSELECT {value};\n```",
            }
            for value in range(3)
        ]
        self.assertEqual(
            executed_sql(history, strict=False, max_round=2),
            ["SELECT 0;", "SELECT 1;"],
        )


if __name__ == "__main__":
    unittest.main()
