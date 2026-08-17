import unittest
from unittest.mock import Mock, patch

from src.client.agents.http_agent import (
    HTTPAgent,
    check_context_limit,
    is_retryable_http_status,
    sanitize_provider_error,
)
from src.typings import AgentClientException, AgentContextLimitException


class HTTPAgentDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.agent = HTTPAgent(
            url="https://example.invalid/v1/chat/completions",
            body={"model": "test-model"},
            headers={"Authorization": "Bearer test"},
            return_format="{response[choices][0][message][content]}",
            prompter={"name": "role_content_dict", "args": {"agent_role": "assistant"}},
        )
        self.history = [{"role": "user", "content": "test"}]

    @patch("src.client.agents.http_agent.requests.post")
    def test_non_retryable_http_error_fails_immediately(self, post):
        response = Mock(status_code=400, text='{"error":"unsupported parameter max_tokens"}')
        post.return_value = response

        with self.assertRaisesRegex(AgentClientException, "HTTP 400.*max_tokens"):
            self.agent.inference(self.history)

        self.assertEqual(post.call_count, 1)

    @patch("src.client.agents.http_agent.time.sleep")
    @patch("src.client.agents.http_agent.requests.post")
    def test_retryable_http_error_retries_three_times(self, post, _sleep):
        post.return_value = Mock(status_code=429, text='{"error":"rate limited"}')

        with self.assertRaisesRegex(Exception, "HTTP 429") as raised:
            self.agent.inference(self.history)

        self.assertIn("attempt 3/3", str(raised.exception))
        self.assertEqual(post.call_count, 3)

    @patch("src.client.agents.http_agent.requests.post")
    def test_context_limit_remains_typed_exception(self, post):
        post.return_value = Mock(
            status_code=400,
            text="Prompt context tokens exceed the maximum context limit",
        )

        with self.assertRaises(AgentContextLimitException):
            self.agent.inference(self.history)

        self.assertEqual(post.call_count, 1)

    @patch("src.client.agents.http_agent.requests.post")
    def test_returns_openai_message_content(self, post):
        response = Mock(status_code=200, text="ok")
        response.json.return_value = {
            "id": "chatcmpl-test",
            "model": "gpt-5-test-snapshot",
            "system_fingerprint": "fp_test",
            "choices": [{"message": {"content": "Action: Answer"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
        }
        post.return_value = response

        self.assertEqual(self.agent.inference(self.history), "Action: Answer")

    @patch("src.client.agents.http_agent.requests.post")
    def test_returns_successful_response_metadata(self, post):
        response = Mock(status_code=200, text="ok")
        response.json.return_value = {
            "id": "chatcmpl-test",
            "model": "gpt-5-test-snapshot",
            "system_fingerprint": "fp_test",
            "choices": [{"message": {"content": "Action: Answer"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
                "completion_tokens_details": {"reasoning_tokens": 2},
            },
        }
        post.return_value = response

        result = self.agent.inference_with_metadata(self.history)

        self.assertEqual(result.content, "Action: Answer")
        self.assertEqual(result.metadata["response_id"], "chatcmpl-test")
        self.assertEqual(result.metadata["model"], "gpt-5-test-snapshot")
        self.assertEqual(result.metadata["finish_reason"], "stop")
        self.assertEqual(result.metadata["usage"]["total_tokens"], 14)

    @patch("src.client.agents.http_agent.time.sleep")
    @patch("src.client.agents.http_agent.requests.post")
    def test_length_limited_empty_content_retries_then_recovers(self, post, _sleep):
        length_response = Mock(status_code=200, text="ok")
        length_response.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"completion_tokens": 512},
        }
        success_response = Mock(status_code=200, text="ok")
        success_response.json.return_value = {
            "choices": [
                {"message": {"content": "Act: answer(1)"}, "finish_reason": "stop"}
            ],
            "usage": {"completion_tokens": 20},
        }
        post.side_effect = [length_response, success_response]

        self.assertEqual(self.agent.inference(self.history), "Act: answer(1)")
        self.assertEqual(post.call_count, 2)

    @patch("src.client.agents.http_agent.time.sleep")
    @patch("src.client.agents.http_agent.requests.post")
    def test_length_limited_empty_content_fails_after_three_attempts(
        self, post, _sleep
    ):
        response = Mock(status_code=200, text="ok")
        response.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
            "usage": {"completion_tokens": 512},
        }
        post.return_value = response

        with self.assertRaisesRegex(AgentClientException, "empty message content") as raised:
            self.agent.inference(self.history)

        self.assertIn("finish_reason='length'", str(raised.exception))
        self.assertIn("completion_tokens", str(raised.exception))
        self.assertIn("attempt 3/3", str(raised.exception))
        self.assertEqual(post.call_count, 3)

    def test_sanitizes_api_key_and_truncates_body(self):
        sanitized = sanitize_provider_error("token sk-secret_123 " + "x" * 2100)

        self.assertNotIn("sk-secret_123", sanitized)
        self.assertIn("sk-<redacted>", sanitized)
        self.assertTrue(sanitized.endswith("...<truncated>"))

    def test_unsupported_max_tokens_is_not_context_limit(self):
        self.assertFalse(check_context_limit("Unsupported parameter: max_tokens"))

    def test_explicit_context_length_error_is_context_limit(self):
        self.assertTrue(
            check_context_limit(
                "This model's maximum context length is 128000 tokens."
            )
        )

    def test_retryable_status_classification(self):
        for status_code in [408, 409, 429, 500, 503]:
            with self.subTest(status_code=status_code):
                self.assertTrue(is_retryable_http_status(status_code))

        for status_code in [400, 401, 403, 404, 422]:
            with self.subTest(status_code=status_code):
                self.assertFalse(is_retryable_http_status(status_code))


if __name__ == "__main__":
    unittest.main()
