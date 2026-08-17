import unittest
from pathlib import Path

from scripts.extract_episode_metrics import extract_episode, summarize


class EpisodeMetadataExtractionTest(unittest.TestCase):
    def test_extracts_and_aggregates_provider_metadata(self):
        row = {
            "index": 7,
            "error": None,
            "output": {
                "status": "completed",
                "result": {
                    "answer": '["ok"]',
                    "type": "other",
                    "error": "",
                    "output_constraint": "c1",
                    "repair_attempts": 1,
                    "repair_successes": 1,
                    "repair_rejection_reasons": ["missing_action"],
                },
                "history": [
                    {"role": "user", "content": "question"},
                    {
                        "role": "agent",
                        "content": "Action: Operation\n```sql\nSELECT 1;\n```",
                        "metadata": {
                            "response_id": "response-1",
                            "model": "gpt-5-snapshot",
                            "finish_reason": "stop",
                            "usage": {
                                "prompt_tokens": 100,
                                "completion_tokens": 30,
                                "total_tokens": 130,
                                "prompt_tokens_details": {"cached_tokens": 25},
                                "completion_tokens_details": {"reasoning_tokens": 20},
                            },
                        },
                    },
                    {"role": "user", "content": "[(1,)]"},
                    {
                        "role": "agent",
                        "content": 'Action: Answer\nFinal Answer: ["ok"]',
                        "metadata": {
                            "response_id": "response-2",
                            "model": "gpt-5-snapshot",
                            "finish_reason": "stop",
                            "usage": {
                                "prompt_tokens": 140,
                                "completion_tokens": 20,
                                "total_tokens": 160,
                                "prompt_tokens_details": {"cached_tokens": 15},
                                "completion_tokens_details": {"reasoning_tokens": 10},
                            },
                        },
                    },
                ],
            },
        }

        episode = extract_episode(row, Path("runs.jsonl"))

        self.assertEqual(episode["input_tokens"], 240)
        self.assertEqual(episode["cached_input_tokens"], 40)
        self.assertEqual(episode["output_tokens"], 50)
        self.assertEqual(episode["reasoning_tokens"], 30)
        self.assertEqual(episode["total_tokens"], 290)
        self.assertEqual(episode["provider_models"], "gpt-5-snapshot")
        self.assertEqual(episode["finish_reasons"], "stop")
        self.assertEqual(episode["provider_response_ids"], "response-1|response-2")
        self.assertEqual(episode["output_constraint"], "c1")
        self.assertEqual(episode["repair_attempts"], 1)
        self.assertEqual(episode["repair_successes"], 1)
        self.assertEqual(episode["repair_rejection_reasons"], "missing_action")

        summary = summarize([episode])
        self.assertEqual(summary["avg_input_tokens"], 240)
        self.assertEqual(summary["avg_cached_input_tokens"], 40)
        self.assertEqual(summary["avg_output_tokens"], 50)
        self.assertEqual(summary["avg_reasoning_tokens"], 30)
        self.assertEqual(summary["avg_total_tokens"], 290)
        self.assertEqual(summary["repair_attempt_rate"], 1.0)
        self.assertEqual(summary["repair_success_rate"], 1.0)

    def test_legacy_history_without_metadata_remains_supported(self):
        row = {
            "index": 1,
            "error": None,
            "output": {
                "status": "completed",
                "result": {"answer": '["ok"]', "type": "other", "error": ""},
                "history": [
                    {"role": "user", "content": "question"},
                    {"role": "agent", "content": 'Action: Answer\nFinal Answer: ["ok"]'},
                ],
            },
        }

        episode = extract_episode(row, Path("legacy.jsonl"))

        self.assertEqual(episode["total_tokens"], 0)
        self.assertEqual(episode["provider_models"], "")


if __name__ == "__main__":
    unittest.main()
