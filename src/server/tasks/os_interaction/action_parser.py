import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParseResult:
    valid: bool
    action: Optional[str] = None
    content: Optional[str] = None
    thought: str = ""
    error: Optional[str] = None


ACTION_LINE = re.compile(r"(?im)^\s*Act:\s*(.+?)\s*$")
THINK_LINE = re.compile(r"(?im)^\s*Think:\s*(.+?)\s*$")
STRICT_BASH = re.compile(
    r"(?is)^\s*(?:Think:\s*.*?\n\s*)?Act:\s*bash\s*\n\s*"
    r"```bash\s*\n(?P<content>.*?)\n```\s*$"
)
STRICT_FINISH = re.compile(
    r"(?is)^\s*(?:Think:\s*.*?\n\s*)?Act:\s*finish\s*$"
)
STRICT_ANSWER = re.compile(
    r"(?is)^\s*(?:Think:\s*.*?\n\s*)?Act:\s*answer\((?P<content>.*)\)\s*$"
)


def _thought(raw: str) -> str:
    return "\n".join(match.strip() for match in THINK_LINE.findall(raw))


def _strict_parse(raw: str) -> ParseResult:
    actions = ACTION_LINE.findall(raw)
    if not actions:
        return ParseResult(False, thought=_thought(raw), error="missing_action")
    if len(actions) != 1:
        return ParseResult(False, thought=_thought(raw), error="multiple_actions")

    action_text = actions[0].strip().lower()
    if action_text == "bash":
        match = STRICT_BASH.fullmatch(raw)
        if not match:
            return ParseResult(False, thought=_thought(raw), error="invalid_bash_envelope")
        content = match.group("content")
        if not content.strip():
            return ParseResult(False, thought=_thought(raw), error="empty_bash_command")
        return ParseResult(True, "bash", content, _thought(raw))
    if action_text == "finish":
        if not STRICT_FINISH.fullmatch(raw):
            return ParseResult(False, thought=_thought(raw), error="invalid_finish_envelope")
        return ParseResult(True, "commit", None, _thought(raw))
    if action_text.startswith("answer"):
        match = STRICT_ANSWER.fullmatch(raw)
        if not match:
            return ParseResult(False, thought=_thought(raw), error="invalid_answer_envelope")
        return ParseResult(True, "commit", match.group("content"), _thought(raw))
    return ParseResult(False, thought=_thought(raw), error="unsupported_action")


def _legacy_parse(raw: str) -> ParseResult:
    thought = _thought(raw)
    for action in reversed(ACTION_LINE.findall(raw)):
        lowered = action.strip().lower()
        if lowered.startswith("bash"):
            blocks = re.findall(r"```bash\s*\n(.*?)\n```", raw, re.DOTALL | re.IGNORECASE)
            return ParseResult(True, "bash", "\n\n".join(blocks), thought)
        if lowered.startswith("finish"):
            return ParseResult(True, "commit", None, thought)
        if lowered.startswith("answer"):
            content = action[6:].strip()
            left = content.find("(")
            right = content.rfind(")")
            if left != -1 and right != -1 and right > left:
                return ParseResult(True, "commit", content[left + 1 : right], thought)
    return ParseResult(False, thought=thought, error="missing_or_unsupported_action")


def parse_osbench_action(raw: str, strict: bool = False) -> ParseResult:
    if not isinstance(raw, str):
        return ParseResult(False, error="non_string_output")
    return _strict_parse(raw) if strict else _legacy_parse(raw)


def build_repair_prompt(error: str) -> str:
    return (
        "Your previous response could not be parsed because "
        f"{error.replace('_', ' ')}. Reply once using exactly one OSBench action: "
        "`Act: bash` followed by one fenced `bash` block, `Act: finish`, or "
        "`Act: answer(...)`. You may include one `Think:` line before the action."
    )
