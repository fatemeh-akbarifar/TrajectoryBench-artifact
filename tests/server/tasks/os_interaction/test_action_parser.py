import unittest

from src.server.tasks.os_interaction.action_parser import (
    build_repair_prompt,
    parse_osbench_action,
)


class OSBenchActionParserTest(unittest.TestCase):
    def test_c0_preserves_legacy_last_action_behavior(self):
        parsed = parse_osbench_action(
            "Act: finish\nThink: revised\nAct: answer(value)", strict=False
        )
        self.assertTrue(parsed.valid)
        self.assertEqual(parsed.action, "commit")
        self.assertEqual(parsed.content, "value")

    def test_c1_accepts_arbitrary_shell_content_inside_one_block(self):
        parsed = parse_osbench_action(
            "Think: inspect safely\nAct: bash\n```bash\n"
            "find /tmp -type f -print0 | xargs -0 -n1 printf '%s\\n'\n```",
            strict=True,
        )
        self.assertTrue(parsed.valid)
        self.assertEqual(parsed.action, "bash")
        self.assertIn("xargs", parsed.content)

    def test_c1_accepts_finish_and_answer(self):
        finish = parse_osbench_action("Think: done\nAct: finish", strict=True)
        answer = parse_osbench_action("Act: answer(a3b0c7)", strict=True)
        self.assertTrue(finish.valid)
        self.assertEqual(finish.action, "commit")
        self.assertIsNone(finish.content)
        self.assertTrue(answer.valid)
        self.assertEqual(answer.content, "a3b0c7")

    def test_c1_rejects_missing_multiple_and_malformed_actions(self):
        cases = [
            ("I am done", "missing_action"),
            ("Act: finish\nAct: answer(x)", "multiple_actions"),
            ("Act: bash\nls -la", "invalid_bash_envelope"),
            ("Act: bash\n```bash\n\n```", "empty_bash_command"),
            ("Act: answer x", "invalid_answer_envelope"),
            ("Act: python", "unsupported_action"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                parsed = parse_osbench_action(raw, strict=True)
                self.assertFalse(parsed.valid)
                self.assertEqual(parsed.error, expected)

    def test_repair_prompt_records_reason_and_allowed_envelopes(self):
        prompt = build_repair_prompt("invalid_bash_envelope")
        self.assertIn("invalid bash envelope", prompt)
        self.assertIn("Act: bash", prompt)
        self.assertIn("Act: finish", prompt)
        self.assertIn("Act: answer", prompt)


if __name__ == "__main__":
    unittest.main()
