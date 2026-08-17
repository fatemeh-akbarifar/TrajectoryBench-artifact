import csv
import tempfile
import unittest
from pathlib import Path

from scripts.build_research_archive import sanitized_csv


class BuildResearchArchiveTest(unittest.TestCase):
    def test_sanitized_csv_removes_text_and_hashes_final_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            destination = root / "sanitized.csv"
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "condition",
                        "official_success",
                        "provider_response_ids",
                        "final_agent_message",
                        "normalized_final_answer",
                        "action_sequence_sha256",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "condition": "P0C0",
                        "official_success": "1",
                        "provider_response_ids": "private-id",
                        "final_agent_message": "private text",
                        "normalized_final_answer": "answer",
                        "action_sequence_sha256": "action-hash",
                    }
                )

            self.assertEqual(sanitized_csv(source, destination, "normalized_final_answer"), 1)
            with destination.open(newline="", encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["condition"], "P0C0")
            self.assertEqual(row["official_success"], "1")
            self.assertEqual(row["action_sequence_sha256"], "action-hash")
            self.assertEqual(len(row["final_outcome_sha256"]), 64)
            self.assertNotIn("provider_response_ids", row)
            self.assertNotIn("final_agent_message", row)
            self.assertNotIn("normalized_final_answer", row)


if __name__ == "__main__":
    unittest.main()
