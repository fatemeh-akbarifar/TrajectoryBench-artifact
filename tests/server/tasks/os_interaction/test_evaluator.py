import asyncio
import base64
import socket
import struct
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from src.server.tasks.os_interaction.task import (
    JudgeConfig,
    OSBenchShellTransportError,
    OSInteraction,
    classify_checker_exit_code,
    atomic_shell_command,
    receive_docker_frame,
    resolve_task_image,
)
from src.typings import AgentOutput, ChatHistoryItem, SampleStatus


class Response:
    def __init__(self, exit_code, output=b""):
        self.exit_code = exit_code
        self.output = output


class FakeContainer:
    def __init__(self, responses=None, exception=None):
        self.responses = list(responses or [])
        self.exception = exception

    def execute_independent(self, script, *params):
        if self.exception:
            raise self.exception
        return self.responses.pop(0)

    def execute(self, command):
        return Response(0, b"still working")


class FakeSession:
    def __init__(self, output):
        self.outputs = list(output) if isinstance(output, list) else [output]
        self.history = []

    def inject(self, item):
        self.history.append(ChatHistoryItem.parse_obj(item))

    async def action(self):
        output = self.outputs.pop(0)
        result = AgentOutput(content=output)
        self.history.append(ChatHistoryItem(role="agent", content=output))
        return result


def make_task(output_constraint="c0", max_repair_attempts=0):
    task = OSInteraction.__new__(OSInteraction)
    task.round_limit = 1
    task.output_constraint = output_constraint
    task.max_repair_attempts = max_repair_attempts
    return task


def make_check_config():
    config = JudgeConfig()
    config.description = "Complete the test task."
    config.init_script = []
    config.start = None
    config.match = None
    config.check = [("bash", "exit 0")]
    config.example_script = None
    return config


class OSBenchEvaluatorTest(unittest.TestCase):
    def test_command_timeout_repeats_interrupt_until_prompt_recovers(self):
        class DelayedInterruptSocket:
            def __init__(self):
                prompt = b"\x1b[0mroot@container:# "
                frames = [b"command echo", socket.timeout(), socket.timeout(), prompt]
                self.chunks = []
                self.sent = []
                for item in frames:
                    if isinstance(item, BaseException):
                        self.chunks.append(item)
                    else:
                        self.chunks.append(struct.pack(">BxxxL", 1, len(item)) + item)

            def send(self, payload):
                self.sent.append(payload)
                return len(payload)

            def recv(self, size):
                item = self.chunks[0]
                if isinstance(item, BaseException):
                    self.chunks.pop(0)
                    raise item
                chunk = item[:size]
                self.chunks[0] = item[size:]
                if not self.chunks[0]:
                    self.chunks.pop(0)
                return chunk

        from src.server.tasks.os_interaction.task import Container

        container = Container.__new__(Container)
        container.sock = DelayedInterruptSocket()
        monotonic_values = iter([0, 31, 31, 32, 33, 34])
        with patch(
            "src.server.tasks.os_interaction.task.time.monotonic",
            side_effect=lambda: next(monotonic_values),
        ):
            result = container.execute("grep -R Linux .")

        self.assertEqual(result.exit_code, 0)
        self.assertGreaterEqual(container.sock.sent.count(b"\x03"), 2)

    def test_stateful_shell_waits_through_temporary_output_silence(self):
        class TemporarilySilentSocket:
            def __init__(self):
                prompt = b"\x1b[0mroot@container:# "
                frames = [b"command echo", socket.timeout(), b"42\n" + prompt]
                self.chunks = []
                for item in frames:
                    if isinstance(item, BaseException):
                        self.chunks.append(item)
                    else:
                        self.chunks.append(struct.pack(">BxxxL", 1, len(item)) + item)

            def send(self, payload):
                return len(payload)

            def recv(self, size):
                item = self.chunks[0]
                if isinstance(item, BaseException):
                    self.chunks.pop(0)
                    raise item
                chunk = item[:size]
                self.chunks[0] = item[size:]
                if not self.chunks[0]:
                    self.chunks.pop(0)
                return chunk

        from src.server.tasks.os_interaction.task import Container

        container = Container.__new__(Container)
        container.sock = TemporarilySilentSocket()

        result = container.execute("sleep briefly; echo 42")

        self.assertEqual(result.exit_code, 0)
        self.assertIn(b"42", result.output)

    def test_multiline_shell_action_is_transmitted_as_one_atomic_command(self):
        command = "cd /tmp\nfor item in a b; do\n  echo $item\ndone"
        wire = atomic_shell_command(command)
        self.assertNotIn("\n", wire)
        encoded = wire.split("printf %s ", 1)[1].split(" |", 1)[0]
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), command)
        self.assertIn("__agentbench_errexit=1", wire)
        self.assertIn("set +e", wire)

    def test_docker_frame_reader_accepts_fragmented_header_and_payload(self):
        class FragmentedSocket:
            def __init__(self, chunks):
                self.chunks = list(chunks)

            def recv(self, size):
                chunk = self.chunks.pop(0)
                if len(chunk) > size:
                    self.chunks.insert(0, chunk[size:])
                    return chunk[:size]
                return chunk

        payload = b"command output"
        header = struct.pack(">BxxxL", 1, len(payload))
        sock = FragmentedSocket([header[:3], header[3:], payload[:4], payload[4:]])
        self.assertEqual(receive_docker_frame(sock), payload)

    def test_docker_frame_reader_reports_closed_stream(self):
        class ClosedSocket:
            def recv(self, size):
                return b""

        with self.assertRaisesRegex(
            OSBenchShellTransportError, "closed after 0/8 bytes"
        ):
            receive_docker_frame(ClosedSocket())

    def test_errexit_action_does_not_terminate_stateful_shell(self):
        wire = atomic_shell_command(
            "set -euo pipefail\nexport AGENTBENCH_TEST_STATE=preserved\n"
            "printf '%s' \"${AGENTBENCH_UNSET_VARIABLE:-}\"\nfalse\n"
            "export AGENTBENCH_UNREACHABLE=yes"
        )
        script = (
            f'{wire}\nprintf "alive:%s:%s\\n" '
            '"$AGENTBENCH_TEST_STATE" "${AGENTBENCH_UNREACHABLE:-no}"\n'
        )
        completed = subprocess.run(
            ["bash"], input=script, text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "alive:preserved:no\n")

    def test_explicit_nonzero_exit_stops_action_without_terminating_shell(self):
        wire = atomic_shell_command(
            "export AGENTBENCH_TEST_STATE=preserved\nexit 1\n"
            "export AGENTBENCH_UNREACHABLE=yes"
        )
        script = (
            f'{wire}\nprintf "alive:%s:%s\\n" '
            '"$AGENTBENCH_TEST_STATE" "${AGENTBENCH_UNREACHABLE:-no}"\n'
        )
        completed = subprocess.run(
            ["bash"], input=script, text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "alive:preserved:no\n")

    def test_explicit_zero_exit_stops_action_without_terminating_shell(self):
        wire = atomic_shell_command("exit\nprintf unreachable")
        completed = subprocess.run(
            ["bash"],
            input=f'{wire}\nprintf "alive\\n"\n',
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "alive\n")

    def test_factorial_configuration_is_balanced_and_prespecified(self):
        root = Path(__file__).resolve().parents[4]
        config = yaml.safe_load((root / "configs/tasks/os.yaml").read_text())
        expected = {
            "os-std-p0c0": (8, "c0", 0),
            "os-std-p0c1": (8, "c1", 1),
            "os-std-p1c0": (5, "c0", 0),
            "os-std-p1c1": (5, "c1", 1),
        }
        for name, values in expected.items():
            parameters = config[name]["parameters"]
            self.assertEqual(
                (
                    parameters["round_limit"],
                    parameters["output_constraint"],
                    parameters["max_repair_attempts"],
                ),
                values,
            )
            self.assertEqual(len(parameters["data_config"]["files"]), 7)

    def test_debug_and_smoke_select_original_task_indices(self):
        root = Path(__file__).resolve().parents[4]
        config = yaml.safe_load((root / "configs/tasks/os.yaml").read_text())
        expected_counts = {
            "os-debug-c0": 1,
            "os-debug-c1": 1,
            "os-smoke-p0c0": 6,
            "os-smoke-p0c1": 6,
            "os-smoke-p1c0": 6,
            "os-smoke-p1c1": 6,
        }
        for name, count in expected_counts.items():
            task = OSInteraction(**config[name]["parameters"])
            self.assertEqual(len(task.get_indices()), count)
        smoke = OSInteraction(**config["os-smoke-p0c0"]["parameters"])
        images = {
            item["config"].image for item in smoke.problem_configs.values()
        }
        evaluator_types = {
            item["config"].get_evaluation_type()
            for item in smoke.problem_configs.values()
        }
        self.assertEqual(images, {"local-os/default", "local-os/packages"})
        self.assertEqual(evaluator_types, {"check", "match"})

    def test_selected_indices_reject_duplicates_and_out_of_range_values(self):
        root = Path(__file__).resolve().parents[4]
        config = yaml.safe_load((root / "configs/tasks/os.yaml").read_text())
        parameters = config["os-debug-c0"]["parameters"]
        parameters["data_config"]["files"][0]["indices"] = [0, 0]
        with self.assertRaisesRegex(ValueError, "Duplicate selected indices"):
            OSInteraction(**parameters)

        config = yaml.safe_load((root / "configs/tasks/os.yaml").read_text())
        parameters = config["os-debug-c0"]["parameters"]
        parameters["data_config"]["files"][0]["indices"] = [1]
        with self.assertRaisesRegex(ValueError, "Invalid selected indices"):
            OSInteraction(**parameters)

    def test_resolves_released_local_image_schema(self):
        self.assertEqual(
            resolve_task_image({"local": "packages"}, "local-os"),
            "local-os/packages",
        )
        self.assertEqual(resolve_task_image({}, "local-os"), "local-os/default")
        self.assertEqual(
            resolve_task_image({"image": "external/image:tag"}, "local-os"),
            "external/image:tag",
        )

    def test_checker_exit_code_contract(self):
        self.assertEqual(classify_checker_exit_code(0), "correct")
        self.assertEqual(classify_checker_exit_code(1), "incorrect")
        self.assertEqual(classify_checker_exit_code(126), "incorrect")
        self.assertEqual(classify_checker_exit_code(127), "incorrect")
        self.assertEqual(classify_checker_exit_code(2), "error")

    def test_known_positive_checker_is_completed_and_correct(self):
        result = asyncio.run(
            make_task()._judge(
                FakeSession("Think: done\nAct: finish"),
                make_check_config(),
                FakeContainer([Response(0)]),
            )
        )

        self.assertEqual(result.status, SampleStatus.COMPLETED)
        self.assertTrue(result.result["result"])
        self.assertEqual(result.result["evaluator_status"], "correct")

    def test_known_negative_checker_is_completed_and_incorrect(self):
        result = asyncio.run(
            make_task()._judge(
                FakeSession("Think: done\nAct: finish"),
                make_check_config(),
                FakeContainer([Response(1)]),
            )
        )

        self.assertEqual(result.status, SampleStatus.COMPLETED)
        self.assertFalse(result.result["result"])
        self.assertEqual(result.result["evaluator_status"], "incorrect")

    def test_checker_infrastructure_failure_is_not_scored_as_incorrect(self):
        result = asyncio.run(
            make_task()._judge(
                FakeSession("Think: done\nAct: finish"),
                make_check_config(),
                FakeContainer([Response(2)]),
            )
        )

        self.assertEqual(result.status, SampleStatus.TASK_ERROR)
        self.assertFalse(result.result["result"])
        self.assertEqual(result.result["evaluator_status"], "error")
        self.assertEqual(result.result["checker_exit_code"], 2)

    def test_checker_exception_is_not_scored_as_incorrect(self):
        result = asyncio.run(
            make_task()._judge(
                FakeSession("Think: done\nAct: finish"),
                make_check_config(),
                FakeContainer(exception=RuntimeError("container unavailable")),
            )
        )

        self.assertEqual(result.status, SampleStatus.TASK_ERROR)
        self.assertEqual(result.result["evaluator_status"], "error")
        self.assertIn("RuntimeError", result.result["error"])

    def test_c1_repairs_one_invalid_response_and_records_metadata(self):
        result = asyncio.run(
            make_task("c1", 1)._judge(
                FakeSession(["not an action", "Act: finish"]),
                make_check_config(),
                FakeContainer([Response(0)]),
            )
        )

        self.assertEqual(result.status, SampleStatus.COMPLETED)
        self.assertTrue(result.result["result"])
        self.assertEqual(result.result["output_constraint"], "c1")
        self.assertEqual(result.result["repair_attempts"], 1)
        self.assertEqual(result.result["repair_successes"], 1)
        self.assertEqual(result.result["repair_rejection_reasons"], ["missing_action"])

    def test_c1_rejects_second_invalid_response_without_another_repair(self):
        result = asyncio.run(
            make_task("c1", 1)._judge(
                FakeSession(["not an action", "still not an action"]),
                make_check_config(),
                FakeContainer(),
            )
        )

        self.assertEqual(result.status, SampleStatus.AGENT_VALIDATION_FAILED)
        self.assertEqual(result.result["repair_attempts"], 1)
        self.assertEqual(result.result["repair_successes"], 0)
        self.assertEqual(
            result.result["repair_rejection_reasons"],
            ["missing_action", "missing_action"],
        )

    def test_task_limit_retains_factorial_and_repair_metadata(self):
        result = asyncio.run(
            make_task("c1", 1)._judge(
                FakeSession("Act: bash\n```bash\necho still-working\n```"),
                make_check_config(),
                FakeContainer(),
            )
        )

        self.assertEqual(result.status, SampleStatus.TASK_LIMIT_REACHED)
        self.assertEqual(result.result["output_constraint"], "c1")
        self.assertEqual(result.result["repair_attempts"], 0)
        self.assertEqual(result.result["repair_successes"], 0)
        self.assertEqual(result.result["repair_rejection_reasons"], [])


if __name__ == "__main__":
    unittest.main()
