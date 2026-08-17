import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.audit_osbench_integrity import audit_osbench


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class OSBenchIntegrityAuditTest(unittest.TestCase):
    def test_current_standard_definition_is_complete(self):
        report = audit_osbench(
            REPOSITORY_ROOT / "configs/tasks/os.yaml", REPOSITORY_ROOT
        )

        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["task_count"], 144)
        self.assertEqual(report["evaluation_counts"], {"check": 135, "match": 9})
        self.assertEqual(
            report["image_counts"],
            {"local-os/default": 143, "local-os/packages": 1},
        )
        self.assertEqual(len(report["definition_sha256"]), 64)

    def test_missing_checker_file_fails_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "configs/tasks").mkdir(parents=True)
            (root / "data/os/data").mkdir(parents=True)
            (root / "data/os/scripts").mkdir(parents=True)
            (root / "data/os/dockerfiles").mkdir(parents=True)
            (root / "data/os/dockerfiles/default").write_text("FROM scratch\n")
            (root / "data/os/data/tasks.json").write_text(
                json.dumps(
                    [
                        {
                            "description": "A task",
                            "evaluation": {"check": {"file": "missing.sh"}},
                        }
                    ]
                )
            )
            config = {
                "os-std": {
                    "parameters": {
                        "docker_config": {
                            "localhost": "local-os",
                            "directory": "data/os/dockerfiles",
                        },
                        "data_config": {
                            "files": [
                                {
                                    "problem_file": "data/os/data/*.json",
                                    "script_dir": "data/os/scripts",
                                }
                            ]
                        },
                    }
                }
            }
            config_path = root / "configs/tasks/os.yaml"
            config_path.write_text(yaml.safe_dump(config))

            report = audit_osbench(config_path, root)

        self.assertFalse(report["valid"])
        self.assertTrue(any("missing.sh" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
