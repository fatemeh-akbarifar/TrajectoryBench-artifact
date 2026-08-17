import contextlib
import re
import time
import warnings

import requests
from urllib3.exceptions import InsecureRequestWarning

from src.typings import *
from src.utils import *
from ..agent import AgentClient

old_merge_environment_settings = requests.Session.merge_environment_settings


@contextlib.contextmanager
def no_ssl_verification():
    opened_adapters = set()

    def merge_environment_settings(self, url, proxies, stream, verify, cert):
        # Verification happens only once per connection so we need to close
        # all the opened adapters once we're done. Otherwise, the effects of
        # verify=False persist beyond the end of this context manager.
        opened_adapters.add(self.get_adapter(url))

        settings = old_merge_environment_settings(self, url, proxies, stream, verify, cert)
        settings['verify'] = False

        return settings

    requests.Session.merge_environment_settings = merge_environment_settings

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', InsecureRequestWarning)
            yield
    finally:
        requests.Session.merge_environment_settings = old_merge_environment_settings

        for adapter in opened_adapters:
            try:
                adapter.close()
            except:
                pass


class Prompter:
    @staticmethod
    def get_prompter(prompter: Union[Dict[str, Any], None]):
        # check if prompter_name is a method and its variable
        if not prompter:
            return Prompter.default()
        assert isinstance(prompter, dict)
        prompter_name = prompter.get("name", None)
        prompter_args = prompter.get("args", {})
        if hasattr(Prompter, prompter_name) and callable(
            getattr(Prompter, prompter_name)
        ):
            return getattr(Prompter, prompter_name)(**prompter_args)
        return Prompter.default()

    @staticmethod
    def default():
        return Prompter.role_content_dict()

    @staticmethod
    def batched_role_content_dict(*args, **kwargs):
        base = Prompter.role_content_dict(*args, **kwargs)

        def batched(messages):
            result = base(messages)
            return {key: [result[key]] for key in result}

        return batched

    @staticmethod
    def role_content_dict(
        message_key: str = "messages",
        role_key: str = "role",
        content_key: str = "content",
        user_role: str = "user",
        agent_role: str = "agent",
    ):
        def prompter(messages: List[Dict[str, str]]):
            nonlocal message_key, role_key, content_key, user_role, agent_role
            role_dict = {
                "user": user_role,
                "agent": agent_role,
            }
            prompt = []
            for item in messages:
                prompt.append(
                    {role_key: role_dict[item["role"]], content_key: item["content"]}
                )
            return {message_key: prompt}

        return prompter

    @staticmethod
    def prompt_string(
        prefix: str = "",
        suffix: str = "AGENT:",
        user_format: str = "USER: {content}\n\n",
        agent_format: str = "AGENT: {content}\n\n",
        prompt_key: str = "prompt",
    ):
        def prompter(messages: List[Dict[str, str]]):
            nonlocal prefix, suffix, user_format, agent_format, prompt_key
            prompt = prefix
            for item in messages:
                if item["role"] == "user":
                    prompt += user_format.format(content=item["content"])
                else:
                    prompt += agent_format.format(content=item["content"])
            prompt += suffix
            print(prompt)
            return {prompt_key: prompt}

        return prompter

    @staticmethod
    def claude():
        return Prompter.prompt_string(
            prefix="",
            suffix="Assistant:",
            user_format="Human: {content}\n\n",
            agent_format="Assistant: {content}\n\n",
        )

    @staticmethod
    def palm():
        def prompter(messages):
            return {"instances": [
                Prompter.role_content_dict("messages", "author", "content", "user", "bot")(messages)
            ]}
        return prompter


def check_context_limit(content: str):
    content = content.lower()
    explicit_codes = [
        "context_length_exceeded",
        "max_tokens_exceeded",
    ]
    if any(code in content for code in explicit_codes):
        return True

    mentions_context = "context" in content
    mentions_exceeded_limit = any(
        phrase in content
        for phrase in [
            "context limit",
            "context length",
            "maximum context",
            "too many tokens",
            "token limit",
            "tokens exceed",
            "tokens exceeded",
        ]
    )
    return mentions_context and mentions_exceeded_limit


def sanitize_provider_error(content: str, max_length: int = 2000) -> str:
    """Keep provider diagnostics useful without leaking key-like values."""
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-<redacted>", content)
    if len(sanitized) > max_length:
        return sanitized[:max_length] + "...<truncated>"
    return sanitized


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in {408, 409, 429} or status_code >= 500


class HTTPAgent(AgentClient):
    def __init__(
        self,
        url,
        proxies=None,
        body=None,
        headers=None,
        return_format="{response}",
        prompter=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.url = url
        self.proxies = proxies or {}
        self.headers = headers or {}
        self.body = body or {}
        self.return_format = return_format
        self.prompter = Prompter.get_prompter(prompter)
        if not self.url:
            raise Exception("Please set 'url' parameter")

    def _handle_history(self, history: List[dict]) -> Dict[str, Any]:
        return self.prompter(history)

    @staticmethod
    def _response_metadata(response: Dict[str, Any], choice: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider": "openai-compatible",
            "response_id": response.get("id"),
            "model": response.get("model"),
            "system_fingerprint": response.get("system_fingerprint"),
            "finish_reason": choice.get("finish_reason"),
            "usage": response.get("usage") or {},
        }

    def inference(self, history: List[dict]) -> str:
        return self.inference_with_metadata(history).content

    def inference_with_metadata(self, history: List[dict]) -> AgentOutput:
        attempt_errors = []
        for attempt in range(3):
            try:
                body = self.body.copy()
                body.update(self._handle_history(history))
                with no_ssl_verification():
                    resp = requests.post(
                        self.url, json=body, headers=self.headers, proxies=self.proxies, timeout=120
                    )
                # print(resp.status_code, resp.text)
                if resp.status_code != 200:
                    if check_context_limit(resp.text):
                        raise AgentContextLimitException(resp.text)
                    detail = (
                        "Provider returned HTTP "
                        f"{resp.status_code}: {sanitize_provider_error(resp.text)}"
                    )
                    if not is_retryable_http_status(resp.status_code):
                        raise AgentClientException("provider_request_failed", detail)
                    raise Exception(detail)
            except AgentClientException as e:
                raise e
            except Exception as e:
                error = f"attempt {attempt + 1}/3: {e}"
                attempt_errors.append(error)
                print("Warning:", error)
            else:
                try:
                    resp = resp.json()
                except Exception as e:
                    error = f"attempt {attempt + 1}/3: invalid JSON response: {e}"
                    attempt_errors.append(error)
                    print("Warning:", error)
                else:
                    # Extract content from OpenAI-compatible API response (vLLM)
                    if isinstance(resp, dict) and "choices" in resp and len(resp["choices"]) > 0:
                        choice = resp["choices"][0]
                        message = choice.get("message", {})
                        content = message.get("content", "")
                        if content:
                            return AgentOutput(
                                content=content,
                                metadata=self._response_metadata(resp, choice),
                            )

                        finish_reason = choice.get("finish_reason")
                        usage = resp.get("usage")
                        error = (
                            f"attempt {attempt + 1}/3: provider returned empty message content "
                            f"(finish_reason={finish_reason!r}, usage={usage!r})"
                        )
                        attempt_errors.append(error)
                        print("Warning:", error)
                    else:
                        # Fallback for non-OpenAI response formats.
                        try:
                            return AgentOutput(
                                content=self.return_format.format(response=resp)
                            )
                        except Exception as e:
                            error = (
                                f"attempt {attempt + 1}/3: could not parse provider response: {e}"
                            )
                            attempt_errors.append(error)
                            print("Warning:", error)

            if attempt < 2:
                time.sleep(attempt + 2)

        details = "; ".join(attempt_errors)
        if attempt_errors and all(
            "finish_reason='length'" in error for error in attempt_errors
        ):
            raise AgentClientException("empty_response_length", details)
        raise Exception(f"HTTP agent inference failed after 3 attempts: {details}")
