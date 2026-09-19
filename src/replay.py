# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Replay captured UTF-8 outputs against quality contracts without execution."""

from __future__ import annotations

import json
import pathlib

from src import evaluation

_MANIFEST_KEYS = {"schema_version", "max_total_tokens", "cases"}
_CASE_KEYS = {
    "name",
    "command",
    "input",
    "exit_code",
    "max_tokens",
    "min_savings_percent",
    "must_preserve",
}
_MAX_MANIFEST_BYTES = 1_000_000
_MAX_CASES = 1000


def _resolve(path: pathlib.Path) -> pathlib.Path:
    """Resolve a path, translating symbolic-link loops into validation errors.

    Args:
        path: Path to resolve.

    Returns:
        The absolute path with symbolic links resolved.

    Raises:
        ValueError: Resolving the path encounters a symbolic-link loop.
    """
    try:
        return path.resolve()
    except RuntimeError as error:
        raise ValueError("path contains a symbolic-link loop") from error


def read_capture(path: pathlib.Path, max_bytes: int) -> str:
    """Read a bounded UTF-8 capture without replacing invalid characters.

    Args:
        path: Regular file containing captured command output.
        max_bytes: Positive maximum number of bytes to read.

    Returns:
        The decoded capture, preserving its original text.

    Raises:
        OSError: The file cannot be read.
        UnicodeDecodeError: The capture is not valid UTF-8.
        ValueError: The limit is invalid, the path is not a regular file, or the
            capture exceeds max_bytes.
    """
    # Keep the validation contract strict: bool and int subclasses are invalid.
    # pylint: disable-next=unidiomatic-typecheck
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_output_bytes must be a positive integer")
    if not path.is_file():
        raise ValueError("input must be a regular file")
    with path.open("rb") as source:
        data = source.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("captured output exceeds max_output_bytes")
    return data.decode("utf-8")


def _validate_case(
    case: object, root: pathlib.Path, names: set[str]
) -> tuple[dict, pathlib.Path, evaluation.QualityPolicy]:
    """Validate a case and reserve its unique name in names.

    Args:
        case: Decoded manifest entry to validate.
        root: Resolved manifest directory that contains all allowed captures.
        names: Previously validated names; updated with this case's name.

    Returns:
        The validated entry, resolved input path, and quality policy.

    Raises:
        ValueError: The entry, policy, input path, or unique name is invalid.
    """
    if not isinstance(case, dict) or case.keys() - _CASE_KEYS:
        raise ValueError(
            "each case must be an object with only supported fields"
        )
    for field in ("name", "command", "input"):
        if not isinstance(case.get(field), str) or not case[field].strip():
            raise ValueError(f"each case needs a non-empty {field}")
    if case["name"] in names:
        raise ValueError("case names must be unique")
    names.add(case["name"])
    exit_code = case.get("exit_code")
    # JSON booleans must not be treated as command exit statuses.
    # pylint: disable-next=unidiomatic-typecheck
    if exit_code is not None and type(exit_code) is not int:
        raise ValueError("exit_code must be an integer or null")
    required = case.get("must_preserve", [])
    if not isinstance(required, list):
        raise ValueError("must_preserve must be an array of non-empty strings")
    policy = evaluation.QualityPolicy(
        max_tokens=case.get("max_tokens"),
        min_savings_percent=case.get("min_savings_percent"),
        must_preserve=tuple(required),
    )
    relative = pathlib.Path(case["input"])
    path = _resolve(root / relative)
    if (
        relative.is_absolute()
        or not path.is_relative_to(root)
        or not path.is_file()
    ):
        raise ValueError("input must name a file inside the manifest directory")
    return case, path, policy


def replay(
    manifest_path: pathlib.Path,
    engine: evaluation.Compressor,
    *,
    chars_per_token: float = 4,
    max_input_bytes: int = 10_000_000,
) -> dict:
    """Evaluate captures and return per-case and aggregate quality verdicts.

    Args:
        manifest_path: UTF-8 JSON manifest stored alongside its captures.
        engine: Compressor to invoke once for each validated capture.
        chars_per_token: Positive, finite character-to-token estimation ratio.
        max_input_bytes: Maximum bytes allowed in each capture.

    Returns:
        A JSON-serializable report containing per-case measurements, aggregate
        token estimates, and pass/fail verdicts. It includes case names but no
        commands, captured output, or required preservation strings.

    Raises:
        OSError: The manifest or a capture cannot be read.
        UnicodeDecodeError: The manifest or a capture is not valid UTF-8.
        ValueError: A manifest field, capture path, size, or estimation ratio is
            invalid, including malformed JSON and duplicate case names.
    """
    manifest_path = _resolve(manifest_path)
    try:
        manifest = json.loads(read_capture(manifest_path, _MAX_MANIFEST_BYTES))
    except RecursionError as error:
        raise ValueError("manifest JSON nesting is too deep") from error
    if not isinstance(manifest, dict) or manifest.keys() - _MANIFEST_KEYS:
        raise ValueError(
            "manifest must be an object with only supported fields"
        )
    if (
        # JSON true compares equal to 1 but is not a schema version.
        # pylint: disable-next=unidiomatic-typecheck
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
    ):
        raise ValueError("schema_version must be 1")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= _MAX_CASES:
        raise ValueError(
            f"cases must contain between 1 and {_MAX_CASES} entries"
        )
    total_limit = manifest.get("max_total_tokens")
    evaluation.QualityPolicy(max_tokens=total_limit)
    names: set[str] = set()
    validated = [
        _validate_case(case, manifest_path.parent, names) for case in cases
    ]
    reports = []
    for case, path, policy in validated:
        output = read_capture(path, max_input_bytes)
        result = evaluation.evaluate(
            engine,
            case["command"],
            output,
            policy=policy,
            exit_code=case.get("exit_code"),
            chars_per_token=chars_per_token,
        )
        reports.append({"name": case["name"], **result.report()})
    original = sum(item["original_tokens"] for item in reports)
    compressed = sum(item["compressed_tokens"] for item in reports)
    violations = (
        ["max_total_tokens"]
        if total_limit is not None and compressed > total_limit
        else []
    )
    return {
        "schema_version": 1,
        "passed": not violations and all(item["passed"] for item in reports),
        "cases": reports,
        "totals": {
            "cases": len(reports),
            "passed": sum(item["passed"] for item in reports),
            "failed": sum(not item["passed"] for item in reports),
            "original_tokens": original,
            "compressed_tokens": compressed,
            "saved_tokens": original - compressed,
            "max_total_tokens": total_limit,
            "violations": violations,
        },
    }
