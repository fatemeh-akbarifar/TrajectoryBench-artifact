import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedDBBenchAction:
    kind: str
    sql: str = ""
    answer: str = ""


@dataclass(frozen=True)
class ParseResult:
    action: Optional[ParsedDBBenchAction]
    error: str = ""

    @property
    def valid(self) -> bool:
        return self.action is not None


def parse_dbbench_action(content: str, strict: bool = False) -> ParseResult:
    content = content or ""
    action_match = re.search(r"Action: (.*?)\n", content)
    action_kind = action_match.group(1) if action_match else ""

    if action_kind == "Operation":
        sql_match = re.search(r"```sql\n([\s\S]*?)\n```", content)
        if not sql_match:
            return ParseResult(None, "missing_sql_code_block")
        raw_sql = sql_match.group(1).strip()
        if strict and "\n" in raw_sql:
            return ParseResult(None, "sql_must_be_one_line")
        return ParseResult(
            ParsedDBBenchAction(kind="operation", sql=raw_sql.replace("\n", " "))
        )

    answer_match = re.search(r"\nFinal Answer:(.*)", content)
    if strict and action_kind != "Answer":
        if not action_match:
            return ParseResult(None, "missing_action")
        return ParseResult(None, "unsupported_action")
    if answer_match:
        return ParseResult(
            ParsedDBBenchAction(kind="answer", answer=answer_match.group(1))
        )

    if action_kind == "Answer":
        return ParseResult(None, "missing_final_answer")
    if action_match:
        return ParseResult(None, "unsupported_action")
    return ParseResult(None, "missing_action")


def build_repair_prompt(error: str) -> str:
    return f"""Your previous response failed the required DBBench action format ({error}).
Return exactly one corrected action using one of these formats:

Action: Operation
```sql
SELECT ...;
```

or

Action: Answer
Final Answer: [\"ANSWER1\", \"ANSWER2\", ...]

Do not discuss the formatting error and do not include more than one action."""
