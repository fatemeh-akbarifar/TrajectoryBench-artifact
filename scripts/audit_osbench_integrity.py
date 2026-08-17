import argparse
import glob
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from src.server.tasks.os_interaction.task import resolve_task_image


def _items(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    raise ValueError(f"{path} must contain one task object or a list of task objects")


def _script_path(script: Any, script_dir: Path) -> Optional[Path]:
    if isinstance(script, dict) and "file" in script:
        return script_dir / script["file"]
    return None


def audit_osbench(config_path: Path, repository_root: Path) -> Dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    definition = config.get("os-std")
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(definition, dict):
        return {"valid": False, "errors": ["os-std definition is missing"], "warnings": []}

    parameters = definition.get("parameters", {})
    data_files = parameters.get("data_config", {}).get("files", [])
    docker_config = parameters.get("docker_config", {})
    docker_dir = repository_root / docker_config.get("directory", "")
    image_prefix = docker_config.get("localhost")
    if not image_prefix:
        errors.append("docker_config.localhost is missing")
    if not docker_dir.is_dir():
        errors.append(f"Dockerfile directory does not exist: {docker_dir}")

    task_count = 0
    evaluation_counts: Counter = Counter()
    image_counts: Counter = Counter()
    referenced_scripts = set()
    source_files = []

    for file_config in data_files:
        pattern = repository_root / file_config["problem_file"]
        matches = sorted(Path(path) for path in glob.glob(str(pattern)))
        if not matches:
            errors.append(f"Problem-file pattern matched no files: {file_config['problem_file']}")
            continue
        script_dir = repository_root / file_config["script_dir"]
        if not script_dir.is_dir():
            errors.append(f"Script directory does not exist: {script_dir}")
        for path in matches:
            source_files.append(path)
            for position, item in enumerate(_items(path)):
                task_count += 1
                location = f"{path.relative_to(repository_root)}#{position}"
                if not isinstance(item.get("description"), str) or not item["description"].strip():
                    errors.append(f"{location}: description is missing")
                evaluation = item.get("evaluation")
                if not isinstance(evaluation, dict):
                    errors.append(f"{location}: evaluation is missing")
                    continue
                modes = [mode for mode in ("check", "match") if mode in evaluation]
                if len(modes) != 1:
                    errors.append(f"{location}: evaluation must define exactly one of check or match")
                    continue
                mode = modes[0]
                evaluation_counts[mode] += 1
                create = item.get("create", {})
                if not isinstance(create, dict):
                    errors.append(f"{location}: create must be an object")
                    create = {}
                image = resolve_task_image(create, image_prefix)
                image_counts[image] += 1

                scripts: Iterable[Any] = []
                if mode == "check":
                    check = evaluation["check"]
                    scripts = check if isinstance(check, list) else [check]
                    if any(script is None for script in scripts) and "example" not in evaluation:
                        errors.append(f"{location}: null checker has no example fallback")
                init = create.get("init")
                if init is not None:
                    scripts = list(scripts) + (init if isinstance(init, list) else [init])
                if "start" in item:
                    scripts = list(scripts) + [item["start"]]
                if "example" in evaluation:
                    scripts = list(scripts) + [evaluation["example"]]
                for script in scripts:
                    referenced = _script_path(script, script_dir)
                    if referenced is not None:
                        referenced_scripts.add(referenced)
                        if not referenced.is_file():
                            errors.append(f"{location}: referenced script does not exist: {referenced}")

    dockerfiles = sorted(path for path in docker_dir.glob("*") if path.is_file())
    available_images = {f"{image_prefix}/{path.name}" for path in dockerfiles}
    for image in image_counts:
        if image.startswith(f"{image_prefix}/") and image not in available_images:
            errors.append(f"No Dockerfile found for configured image: {image}")

    if task_count != 144:
        warnings.append(f"Expected 144 os-std tasks but found {task_count}")

    digest = hashlib.sha256()
    definition_files = {
        path
        for path in set(source_files) | referenced_scripts | set(dockerfiles)
        if path.is_file()
    }
    for path in sorted(definition_files):
        digest.update(str(path.relative_to(repository_root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    return {
        "valid": not errors,
        "task_count": task_count,
        "evaluation_counts": dict(sorted(evaluation_counts.items())),
        "image_counts": dict(sorted(image_counts.items())),
        "problem_file_count": len(source_files),
        "referenced_script_count": len(referenced_scripts),
        "dockerfile_count": len(dockerfiles),
        "definition_sha256": digest.hexdigest(),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the static OSBench execution definition")
    parser.add_argument("--config", type=Path, default=Path("configs/tasks/os.yaml"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_osbench(args.config, args.repository_root.resolve())
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
