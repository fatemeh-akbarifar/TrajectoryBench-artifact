import asyncio
import unittest

from src.server.tasks.dbbench import DBBench
from src.typings import AgentOutput, ChatHistoryItem, SampleStatus


class FakeContainer:
    def __init__(self):
        self.executed = []

    def execute(self, sql, database=None, data=()):
        self.executed.append((sql, database, data))
        if sql == "SELECT Notes FROM `test_table` WHERE Method = 'decision';":
            return "[('value',)]"
        return ""

    def fetch_all(self, sql, database=None):
        self.executed.append((sql, database, ()))
        return [("value",)]


class FakeSession:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.history = []

    def inject(self, item):
        if not item:
            return
        self.history.append(ChatHistoryItem.parse_obj(item))

    async def action(self):
        output = self.outputs.pop(0)
        self.history.append(
            ChatHistoryItem(
                role="agent",
                content=output.content or output.status,
                metadata=output.metadata,
            )
        )
        return output


def make_task(output_constraint, max_repair_attempts):
    task = DBBench.__new__(DBBench)
    task.max_round = 15
    task.output_constraint = output_constraint
    task.max_repair_attempts = max_repair_attempts
    task.container = FakeContainer()
    entry = {
        "type": ["other"],
        "description": "Find the notes.",
        "add_description": "Use the test table.",
        "table": {
            "table_name": "test_table",
            "table_info": {
                "columns": [
                    {"name": "Method"},
                    {"name": "Notes"},
                ],
                "rows": [["decision", "value"]],
            },
        },
    }
    task.dataset = [(entry, ["value"])]
    return task


class DBBenchOutputConstraintTest(unittest.TestCase):
    def test_c0_invalid_output_fails_without_repair(self):
        task = make_task("c0", 0)
        session = FakeSession([AgentOutput(content="invalid")])

        result = asyncio.run(task.start_sample(0, session))

        self.assertEqual(result.status, SampleStatus.AGENT_VALIDATION_FAILED)
        self.assertEqual(result.result["repair_attempts"], 0)
        self.assertEqual(result.result["repair_successes"], 0)
        self.assertEqual(result.result["repair_rejection_reasons"], ["missing_action"])

    def test_c1_repairs_once_and_completes(self):
        task = make_task("c1", 1)
        session = FakeSession(
            [
                AgentOutput(content="invalid"),
                AgentOutput(
                    content=(
                        "Action: Operation\n```sql\n"
                        "SELECT Notes FROM `test_table` WHERE Method = 'decision';\n```"
                    )
                ),
                AgentOutput(content='Action: Answer\nFinal Answer: ["value"]'),
            ]
        )

        result = asyncio.run(task.start_sample(0, session))

        self.assertEqual(result.status, SampleStatus.COMPLETED)
        self.assertEqual(result.result["answer"], ' ["value"]')
        self.assertEqual(result.result["repair_attempts"], 1)
        self.assertEqual(result.result["repair_successes"], 1)
        repair_prompts = [
            item.content
            for item in session.history
            if item.role == "user" and "previous response failed" in item.content
        ]
        self.assertEqual(len(repair_prompts), 1)

    def test_c1_does_not_allow_second_repair(self):
        task = make_task("c1", 1)
        session = FakeSession(
            [
                AgentOutput(content="invalid"),
                AgentOutput(content="still invalid"),
            ]
        )

        result = asyncio.run(task.start_sample(0, session))

        self.assertEqual(result.status, SampleStatus.AGENT_VALIDATION_FAILED)
        self.assertEqual(result.result["repair_attempts"], 1)
        self.assertEqual(result.result["repair_successes"], 0)
        self.assertEqual(
            result.result["repair_rejection_reasons"],
            ["missing_action", "missing_action"],
        )


if __name__ == "__main__":
    unittest.main()
