import unittest

from src.assigner import redact_config_secrets


class AssignerConfigRedactionTest(unittest.TestCase):
    def test_redacts_nested_credentials_without_mutating_runtime_config(self):
        config = {
            "definition": {
                "agent": {
                    "gpt-5": {
                        "parameters": {
                            "headers": {
                                "Authorization": "Bearer live-secret",
                                "Content-Type": "application/json",
                            },
                            "api_key": "live-api-key",
                            "body": {
                                "model": "gpt-5",
                                "max_completion_tokens": 1024,
                            },
                        }
                    }
                }
            }
        }

        persisted = redact_config_secrets(config)

        headers = persisted["definition"]["agent"]["gpt-5"]["parameters"]["headers"]
        parameters = persisted["definition"]["agent"]["gpt-5"]["parameters"]
        self.assertEqual(headers["Authorization"], "<redacted>")
        self.assertEqual(parameters["api_key"], "<redacted>")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(parameters["body"]["model"], "gpt-5")
        self.assertEqual(parameters["body"]["max_completion_tokens"], 1024)
        self.assertEqual(
            config["definition"]["agent"]["gpt-5"]["parameters"]["headers"][
                "Authorization"
            ],
            "Bearer live-secret",
        )

    def test_redacts_credentials_nested_in_lists(self):
        config = [{"client_secret": "secret-value"}, {"temperature": 1}]

        self.assertEqual(
            redact_config_secrets(config),
            [{"client_secret": "<redacted>"}, {"temperature": 1}],
        )


if __name__ == "__main__":
    unittest.main()
