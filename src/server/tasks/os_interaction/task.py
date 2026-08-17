import asyncio
import base64
import copy
import glob
import json
import os
import re
import socket
import struct
import time
from typing import List, Dict, Any, Tuple

import docker
import docker.models.containers

from src.server.task import Task, Session
from src.typings import (
    AgentOutputStatus,
    TaskOutput,
    TaskSampleExecutionResult,
    SampleStatus,
)
from .action_parser import build_repair_prompt, parse_osbench_action


def classify_checker_exit_code(exit_code: int) -> str:
    """Classify the exit-code contract used by OSBench checker scripts."""
    if exit_code == 0:
        return "correct"
    if exit_code in {1, 126, 127}:
        return "incorrect"
    return "error"


def resolve_task_image(create: Dict[str, Any], image_prefix: str) -> str:
    """Resolve the image schema used by the released OSBench task data."""
    if "image" in create:
        return create["image"]
    return f"{image_prefix}/{create.get('local', 'default')}"


def atomic_shell_command(command: str) -> str:
    """Encode and guard one model action in the persistent interactive shell."""
    encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
    return (
        f'__agentbench_payload="$(printf %s {encoded} | base64 -d)"; '
        '__agentbench_errexit=0; __agentbench_explicit_exit=0; '
        '__agentbench_status=0; builtin set -E; '
        'set() { if [ "$#" -ge 1 ]; then case "$1" in -*[eu]*) '
        'case "$1" in *e*) __agentbench_errexit=1;; esac; '
        '__agentbench_options="${1//e/}"; '
        '__agentbench_options="${__agentbench_options//u/}"; shift; '
        'if [ "$__agentbench_options" != "-" ]; then '
        'builtin set "$__agentbench_options" "$@"; fi; return 0;; '
        '+*[eu]*) case "$1" in *e*) __agentbench_errexit=0;; esac; '
        '__agentbench_options="${1//e/}"; '
        '__agentbench_options="${__agentbench_options//u/}"; shift; '
        'if [ "$__agentbench_options" != "+" ]; then '
        'builtin set "$__agentbench_options" "$@"; fi; return 0;; '
        'esac; fi; builtin set "$@"; }; '
        'exit() { __agentbench_status="${1:-$?}"; '
        '__agentbench_explicit_exit=1; return 125; }; '
        "trap '__agentbench_failure=$?; if [ \"$__agentbench_explicit_exit\" -eq 1 ]; "
        'then __agentbench_explicit_exit=0; return "$__agentbench_status"; '
        'elif [ "$__agentbench_errexit" -eq 1 ]; then '
        '__agentbench_status="$__agentbench_failure"; '
        '__agentbench_errexit=0; return "$__agentbench_status"; '
        "else :; fi' ERR; "
        '__agentbench_action() { eval "$__agentbench_payload"; }; '
        '__agentbench_action; trap - ERR; builtin set +E; '
        'unset -f set exit __agentbench_action; '
        'unset __agentbench_payload __agentbench_errexit '
        '__agentbench_explicit_exit __agentbench_options '
        '__agentbench_failure; set +e; '
        '(exit "$__agentbench_status")'
    )


class OSBenchShellTransportError(RuntimeError):
    """Raised when the persistent Docker exec stream closes unexpectedly."""


def receive_exact(sock, size: int) -> bytes:
    """Read one complete Docker stream frame component or fail clearly."""
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            received = size - remaining
            raise OSBenchShellTransportError(
                f"Docker shell stream closed after {received}/{size} bytes"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_docker_frame(sock) -> bytes:
    """Read and decode one complete Docker multiplexed-stream frame."""
    header = receive_exact(sock, 8)
    _, length = struct.unpack(">BxxxL", header)
    return receive_exact(sock, length)


class Container:
    def __init__(self, image):
        self.image = image
        self.client = docker.from_env()
        self.container: docker.models.containers.Container = self.client.containers.run(
            image,
            detach=True,
            tty=True,
            stdin_open=True,
            remove=True,
            labels={"created_by": "os-pipeline"},
        )
        self.exec_id = self.client.api.exec_create(
            self.container.id, "bash --login", stdin=True, tty=True
        )["Id"]
        self.sock = self.client.api.exec_start(self.exec_id, socket=True)._sock
        self.sock.settimeout(5)
        # clear buffer
        self.sock.recv(1000)

    def __del__(self):
        try:
            self.container.stop()
        except:
            pass

    def execute(self, command: str):
        class DummyOutput:
            output: bytes
            exit_code: int

            def __init__(self, code, o):
                self.output = o
                self.exit_code = code

        # print("=== EXECUTING ===\n", command)
        if not isinstance(command, str):
            return DummyOutput(-1, b"")
        wire_command = atomic_shell_command(command)
        self.sock.send(wire_command.encode("utf-8") + b"\n")
        # ignore input line
        _ = receive_docker_frame(self.sock)

        time_limit = 30  # seconds
        start_time = time.monotonic()

        output = b""
        while True:
            if time.monotonic() - start_time > time_limit:
                print(f"Time limit reached, breaking out of the loop. Command was: `{command}`")
                # A persistent shell must be returned to its prompt before the
                # next action is sent. Otherwise, that action can be consumed by
                # the still-running command and the Docker stream desynchronizes.
                self.sock.send(b"\x03")
                interrupt_deadline = time.monotonic() + 30
                while time.monotonic() < interrupt_deadline:
                    try:
                        line = receive_docker_frame(self.sock)
                        output += line
                        if re.search(b"\x1b.+@.+[#|$] ", line):
                            break
                    except (TimeoutError, socket.timeout):
                        # A process blocked in filesystem I/O may not react to
                        # the first terminal interrupt immediately. Repeating
                        # Ctrl-C is bounded by the recovery deadline and does
                        # not extend the command's execution allowance.
                        self.sock.send(b"\x03")
                        continue
                else:
                    raise OSBenchShellTransportError(
                        "Docker shell did not return to its prompt after command timeout"
                    )
                break
            try:
                line = receive_docker_frame(self.sock)
                output += line
                if re.search(b"\x1b.+@.+[#|$] ", line):
                    break
            except (TimeoutError, socket.timeout):
                # Five seconds without output does not mean that the command
                # finished. Continue polling until output/prompt or the command
                # deadline above.
                continue

        # Clean up the output by removing terminal control sequences, removes escape sequences starting with
        # ESC (0x1b), followed by...
        # ... any characters, an '@' character, any characters, ending with '#' or '$'
        output = re.sub(b"\x1b.+@.+[#|$] ", b'', output)
        # ... '[' and any combination of digits and semicolons, ending with a letter (a-z or A-Z)
        output = re.sub(b'\x1b\\[[0-9;]*[a-zA-Z]', b'', output)
        # ... ']' and any digits, a semicolon, any characters except BEL (0x07), and ending with BEL
        output = re.sub(b'\x1b\\][0-9]*;[^\x07]*\x07', b'', output)
        # ... '[?2004' and either 'h' or 'l'
        output = re.sub(b'\x1b\[\?2004[hl]', b'', output)

        # Remove BEL characters (0x07)
        output = re.sub(b'\x07', b'', output)

        return DummyOutput(0, output)

    def execute_independent(self, command, *params):
        # print("=== EXECUTING INDEPENDENT ===\n", command)
        language, command = command
        # if params:
        #     print("== Parameters ==\n", params)
        if language == "bash":
            cmd = ["bash", "-c", command]
            if params:
                cmd.append("--")
                cmd.extend(params)
        elif language == "python":
            cmd = ["python3", "-c", command, *params]
        elif language == "c++":
            self.execute_independent(
                (
                    "bash",
                    f'echo "{json.dumps(command)}" > /tmp/main.cpp && '
                    f"g++ -o /tmp/a.out /tmp/main.cpp",
                ),
                None,
            )
            cmd = ["/tmp/a.out", *params]
        elif language == "c":
            self.execute_independent(
                (
                    "bash",
                    f'echo "{json.dumps(command)}" > /tmp/main.cpp && '
                    f"gcc -o /tmp/a.out /tmp/main.cpp",
                ),
                None,
            )
            cmd = ["/tmp/a.out", *params]
        else:
            raise ValueError("Unsupported language")
        return self.container.exec_run(cmd)


class JudgeConfig:
    image: str = None
    init_script: List[Tuple[str, str]] = None
    start: Tuple[str, str] = None
    description: str
    check: list = None
    match: dict = None
    example_script: str = None

    def get_evaluation_type(self):
        if self.check:
            return "check"
        elif self.match:
            return "match"

    def get_evaluation_content(self):
        return self.check or self.match


ONE_SHOT = [
    {"role": "user", "content": 'tell me how many files are in the directory "/etc"?'},
    {
        "role": "agent",
        "content": """Think: To count the files in /etc, I need to print all the files in it.

Act: bash

```bash
ls /etc
```""",
    },
    {
        "role": "user",
        "content": "The output of the OS:\ncpi cron.hourly fuse.conf iproute2 lvm networkd-dispatcher protocols "
                   "selinux tmpfiles.d [truncated because the output is too long]",
    },
    {
        "role": "agent",
        "content": """Think: The output has been truncated because it is too long, so I need to count files by script directly.

Act: bash

```bash
ls -1 /etc | wc -l
```""",
    },
    {"role": "user", "content": "The output of the OS:\n220"},
    {
        "role": "agent",
        "content": """Think: Now I get the answer, it is 220.

Act: answer(220)""",
    },
]


class OSInteraction(Task):
    def _load_configs(self, config_path, script_root_dir=".") -> List[JudgeConfig]:
        def load_script(script_obj):
            if script_obj is None:
                return None
            if type(script_obj) is str:
                return "bash", script_obj
            if "language" not in script_obj:
                language = "bash"
            else:
                language = script_obj["language"]
            if "file" in script_obj:
                with open(
                    os.path.join(script_root_dir, script_obj["file"]), encoding="utf-8"
                ) as f:
                    return language, f.read()
            elif "code" in script_obj:
                return language, script_obj["code"]
            else:
                raise ValueError("Invalid Script Object")

        # 1. handle input file:
        if config_path.endswith(".json"):
            with open(config_path, encoding="utf-8") as f:
                config_raw = json.load(f)
            if isinstance(config_raw, list):
                pass
            elif isinstance(config_raw, dict):
                config_raw = [config_raw]
            else:
                raise ValueError("Invalid Config File")
        elif config_path.endswith(".jsonl"):
            with open(config_path, encoding="utf-8") as f:
                config_raw = [json.loads(line) for line in f.readlines()]
        else:
            raise ValueError("Invalid Config File")

        # 2. handle configs
        configs: list[JudgeConfig] = []
        for item in config_raw:
            config = JudgeConfig()
            config.description = item["description"]
            if "create" in item:
                config.image = resolve_task_image(
                    item["create"], self.docker_config["localhost"]
                )
                if "init" in item["create"]:
                    if type(item["create"]["init"]) is not list:
                        config.init_script = [load_script(item["create"]["init"])]
                    else:
                        config.init_script = [
                            load_script(script_obj)
                            for script_obj in item["create"]["init"]
                        ]
                else:
                    config.init_script = []
            else:
                config.image = self.docker_config["localhost"] + "/default"
            if "start" in item:
                config.start = load_script(item["start"])
            evaluation = item["evaluation"]
            if "match" in evaluation:
                if type(evaluation["match"]) is str:
                    config.match = {"answer": evaluation["match"], "strip": True}
                else:
                    config.match = evaluation["match"]
            elif "check" in evaluation:
                if type(evaluation["check"]) is not list:
                    config.check = [load_script(evaluation["check"])]
                else:
                    config.check = [
                        load_script(script_obj) for script_obj in evaluation["check"]
                    ]
            else:
                raise ValueError("check or match must exist.")
            if "check" in evaluation and "example" in evaluation:
                config.example_script = load_script(evaluation["example"])
            configs.append(config)
        return configs

    def __init__(
        self,
        data_config,
        docker_config,
        round_limit=8,
        output_constraint="c0",
        max_repair_attempts=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.round_limit: int = round_limit
        self.output_constraint = output_constraint.lower()
        if max_repair_attempts is None:
            max_repair_attempts = 1 if self.output_constraint == "c1" else 0
        self.max_repair_attempts = max_repair_attempts
        if self.output_constraint not in {"c0", "c1"}:
            raise ValueError("output_constraint must be 'c0' or 'c1'")
        if self.max_repair_attempts not in {0, 1}:
            raise ValueError("max_repair_attempts must be 0 or 1")
        if self.output_constraint == "c0" and self.max_repair_attempts != 0:
            raise ValueError("C0 cannot enable repair attempts")
        self.data_config = copy.deepcopy(data_config)
        self.docker_config = copy.deepcopy(docker_config)
        self.problem_configs: Dict[str, Dict[str, Any]] = {}  # {index: CONFIG}

        matches = []
        for item in self.data_config["files"]:
            path = item["problem_file"]
            for file in glob.glob(path):
                if file.endswith(".json") or file.endswith(".jsonl"):
                    matches.append(
                        {
                            "problem_file": file,
                            "script_dir": item["script_dir"],
                            "index_prefix": item["index_prefix"]
                            + os.path.basename(file)
                            .removesuffix(".json")
                            .removesuffix(".jsonl")
                            + "-",
                            "indices": item.get("indices"),
                        }
                    )
        self.data_config["files"] = matches

        for item in self.data_config["files"]:
            problem_file = item["problem_file"]
            single_file_configs = self._load_configs(problem_file, item["script_dir"])
            selected_indices = item.get("indices")
            if selected_indices is not None:
                if len(set(selected_indices)) != len(selected_indices):
                    raise ValueError(f"Duplicate selected indices for {problem_file}")
                invalid = [
                    index
                    for index in selected_indices
                    if not isinstance(index, int)
                    or index < 0
                    or index >= len(single_file_configs)
                ]
                if invalid:
                    raise ValueError(
                        f"Invalid selected indices for {problem_file}: {invalid}"
                    )
                selected = set(selected_indices)
            else:
                selected = None
            dict_configs = {}
            for idx, config in enumerate(single_file_configs):
                if selected is not None and idx not in selected:
                    continue
                dict_configs[item["index_prefix"] + "%05d" % idx] = {
                    "file": problem_file,
                    "config": config,
                    "index": idx,
                }
            self.problem_configs.update(dict_configs)

    def calculate_overall(self, results: List[TaskOutput]) -> Dict[str, Any]:
        overall = {
            "total": len([config for config in results if config]),
            "pass": len(
                [
                    config
                    for config in results
                    if (config and config.result and config.result.get("result", False))
                ]
            ),
        }
        overall["wrong"] = overall["total"] - overall["pass"]
        overall["acc"] = overall["pass"] / overall["total"] if overall["total"] else 0
        return {
            "overall": overall,
        }

    def get_indices(self) -> List[Any]:
        return list(self.problem_configs.keys())

    async def start_sample(self, index, session: Session) -> TaskSampleExecutionResult:
        data_item = self.problem_configs[index]
        config = data_item["config"]
        file = data_item["file"]
        index_in_file = data_item["index"]
        try:
            print("init container")
            container = Container(config.image)
            print("init container ok")
            print("start judge")
            result = await self._judge(session, config, container)
            result.result["file"] = file
            result.result["index_in_file"] = index_in_file
            print("finish judge")
            return result
        except Exception as _:
            print("err")
            import traceback

            return TaskSampleExecutionResult(
                status=SampleStatus.TASK_ERROR,
                result={
                    "result": False,
                    "evaluator_status": "error",
                    "error": traceback.format_exc(),
                },
            )
        finally:
            try:
                container.__del__()
            except:
                pass

    async def _judge(
        self, session: Session, config: JudgeConfig, container: Container
    ) -> TaskSampleExecutionResult:

        print("exec start")
        if config.init_script:
            for script in config.init_script:
                init = await asyncio.to_thread(container.execute_independent, script)
                if init.exit_code != 0:
                    return TaskSampleExecutionResult(
                        status=SampleStatus.TASK_ERROR,
                        result={
                            "result": False,
                            "evaluator_status": "error",
                            "error": f"Init script failed with exit code {init.exit_code}",
                        },
                    )
        if config.start:
            start = await asyncio.to_thread(container.execute, config.start[1])
            if start.exit_code != 0:
                return TaskSampleExecutionResult(
                    status=SampleStatus.TASK_ERROR,
                    result={
                        "result": False,
                        "evaluator_status": "error",
                        "error": f"Start script failed with exit code {start.exit_code}",
                    },
                )
        print("exec start ok")

        repair_attempts = 0
        repair_successes = 0
        rejection_reasons = []

        oneshot = True
        session.inject(
            {
                "role": "user",
                "content": """You are an assistant that will act like a person, I'will play the role of linux(ubuntu) operating system. Your goal is to implement the operations required by me or answer to the question proposed by me. For each of your turn, you should first think what you should do, and then take exact one of the three actions: "bash", "finish" or "answer". 

1. If you think you should execute some bash code, take bash action, and you should print like this:

Think: put your thought here.

Act: bash

```bash
# put your bash code here
```

2. If you think you have finished the task, take finish action, and you should print like this:

Think: put your thought here.

Act: finish

3. If you think you have got the answer to the question, take answer action, and you should print like this:

Think: put your thought here.

Act: answer(Your answer to the question should be put in this pair of parentheses)

If the output is too long, I will truncate it. The truncated output is not complete. You have to deal with the truncating problem by yourself. Attention, your bash code should not contain any input operation. Once again, you should take only exact one of the three actions in each turn.\n\n""",
            }
        )

        if not oneshot:
            session.history[-1].content += (
                "Now, my problem is:\n\n" + config.description
            )
        else:
            session.history[-1].content += (
                "Now, my problem is:\n\n" + ONE_SHOT[0]["content"]
            )
            for item in ONE_SHOT[1:]:
                session.inject(item)
            session.inject(
                {
                    "role": "user",
                    "content": "Now, I will start a new problem in a new OS. My problem is:\n\n"
                    + config.description,
                }
            )

        async def receive_valid_action():
            nonlocal repair_attempts, repair_successes
            agent_output = await session.action()
            if agent_output.status == AgentOutputStatus.AGENT_CONTEXT_LIMIT:
                return None, SampleStatus.AGENT_CONTEXT_LIMIT
            if agent_output.status != AgentOutputStatus.NORMAL:
                return None, SampleStatus.UNKNOWN

            strict = self.output_constraint == "c1"
            parsed = parse_osbench_action(agent_output.content or "", strict=strict)
            if parsed.valid:
                return parsed, None
            rejection_reasons.append(parsed.error)
            if not strict or repair_attempts >= self.max_repair_attempts:
                return None, SampleStatus.AGENT_VALIDATION_FAILED

            repair_attempts += 1
            session.inject({"role": "user", "content": build_repair_prompt(parsed.error)})
            repaired_output = await session.action()
            if repaired_output.status == AgentOutputStatus.AGENT_CONTEXT_LIMIT:
                return None, SampleStatus.AGENT_CONTEXT_LIMIT
            if repaired_output.status != AgentOutputStatus.NORMAL:
                return None, SampleStatus.UNKNOWN
            repaired = parse_osbench_action(repaired_output.content or "", strict=True)
            if repaired.valid:
                repair_successes += 1
                return repaired, None
            rejection_reasons.append(repaired.error)
            return None, SampleStatus.AGENT_VALIDATION_FAILED

        for _ in range(self.round_limit):
            parsed, action_failure = await receive_valid_action()
            if action_failure is not None:
                return TaskSampleExecutionResult(
                    status=action_failure,
                    result={
                        "result": False,
                        "output_constraint": self.output_constraint,
                        "repair_attempts": repair_attempts,
                        "repair_successes": repair_successes,
                        "repair_rejection_reasons": rejection_reasons,
                    },
                )

            action = parsed.action
            content = parsed.content
            if action == "commit":
                answer = content
                break
            elif action == "bash":
                result = await asyncio.to_thread(container.execute, content)
                result = result.output.decode("utf-8")
                if len(result) > 800:
                    result = (
                        result[:780] + "\n[truncated because the output is too long]"
                    )
                session.inject(
                    {
                        "role": "user",
                        "content": ("The output of the OS:\n\n" + result)
                        if result
                        else "The output of the OS is empty.",
                    }
                )
        else:
            return TaskSampleExecutionResult(
                status=SampleStatus.TASK_LIMIT_REACHED,
                result={
                    "result": False,
                    "reason": "round limit",
                    "output_constraint": self.output_constraint,
                    "repair_attempts": repair_attempts,
                    "repair_successes": repair_successes,
                    "repair_rejection_reasons": rejection_reasons,
                },
            )

        if isinstance(answer, str) and config.match and config.match["strip"]:
            answer = answer.strip()

        jd = False
        evaluator_status = "incorrect"

        if config.match:
            if "answer" in config.match:
                jd = answer == config.match["answer"]
            elif "regex" in config.match:
                jd = re.search(config.match["regex"], answer) is not None
            evaluator_status = "correct" if jd else "incorrect"
        elif config.check:
            params = [str(answer)]
            for checker_index, script in enumerate(config.check):
                if script is None:
                    script = config.example_script
                try:
                    response = await asyncio.to_thread(
                        container.execute_independent, script, *params
                    )
                except Exception as exc:
                    return TaskSampleExecutionResult(
                        status=SampleStatus.TASK_ERROR,
                        result={
                            "result": False,
                            "evaluator_status": "error",
                            "evaluator_type": "check",
                            "checker_index": checker_index,
                            "error": f"Checker execution raised {type(exc).__name__}: {exc}",
                        },
                    )
                checker_status = classify_checker_exit_code(response.exit_code)
                if checker_status == "error":
                    return TaskSampleExecutionResult(
                        status=SampleStatus.TASK_ERROR,
                        result={
                            "result": False,
                            "evaluator_status": "error",
                            "evaluator_type": "check",
                            "checker_index": checker_index,
                            "checker_exit_code": response.exit_code,
                            "error": "Checker infrastructure error",
                        },
                    )
                if checker_status == "incorrect":
                    jd = False
                    evaluator_status = "incorrect"
                    break
                params.append(response.output.decode("utf-8"))
            else:
                jd = True
                evaluator_status = "correct"
        else:
            return TaskSampleExecutionResult(
                status=SampleStatus.UNKNOWN, result={"result": False}
            )

        return TaskSampleExecutionResult(
            status=SampleStatus.COMPLETED,
            result={
                "result": jd,
                "evaluator_status": evaluator_status,
                "evaluator_type": "match" if config.match else "check",
                "output_constraint": self.output_constraint,
                "repair_attempts": repair_attempts,
                "repair_successes": repair_successes,
                "repair_rejection_reasons": rejection_reasons,
            },
        )
