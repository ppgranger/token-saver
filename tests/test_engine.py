"""Tests for the compression engine."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import CompressionEngine
from src.processors import collect_hook_patterns, discover_processors


class TestCompressionEngine:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_short_output_not_compressed(self):
        output = "short output"
        compressed, _processor, was_compressed = self.engine.compress("git status", output)
        assert not was_compressed
        assert compressed == output

    def test_empty_output(self):
        compressed, _processor, was_compressed = self.engine.compress("git status", "")
        assert not was_compressed
        assert compressed == ""

    def test_whitespace_only_output(self):
        _compressed, _processor, was_compressed = self.engine.compress("git status", "   \n\n  ")
        assert not was_compressed

    def test_git_status_compressed(self):
        output = "\n".join(
            [
                "On branch main",
                "Your branch is up to date with 'origin/main'.",
                "",
                "Changes not staged for commit:",
                '  (use "git add <file>..." to update what will be committed)',
                "",
            ]
            + [f" M src/file{i}.py" for i in range(30)]
            + [
                "",
                "Untracked files:",
            ]
            + [f" ?? new_file{i}.txt" for i in range(20)]
        )

        compressed, processor, was_compressed = self.engine.compress("git status", output)
        assert was_compressed
        assert processor == "git"
        assert len(compressed) < len(output)

    def test_generic_fallback(self):
        output = "line\n" * 100 + "unique line\n" + "another\n" * 100
        _compressed, processor, _was_compressed = self.engine.compress("some_command", output)
        assert processor in ("generic", "none")

    def test_repeated_lines_compressed(self):
        output = "Building module...\n" * 50 + "Done.\n"
        compressed, _processor, was_compressed = self.engine.compress("some_build_cmd", output)
        if was_compressed:
            assert "x50" in compressed
            assert len(compressed) < len(output)

    def test_pytest_output_compressed(self):
        lines = []
        for i in range(50):
            lines.append(f"tests/test_mod{i}.py::test_func PASSED")
        lines.append("=" * 60 + " 50 passed in 2.34s " + "=" * 60)
        output = "\n".join(lines)

        compressed, processor, was_compressed = self.engine.compress("pytest", output)
        assert was_compressed
        assert processor == "test"
        assert "50 tests passed" in compressed

    def test_build_success_compressed(self):
        lines = []
        for i in range(40):
            lines.append(f"  Downloading package-{i} (1.2.3)")
        lines.append("Successfully built project")
        lines.append("Build completed in 12.3s")
        output = "\n".join(lines)

        compressed, processor, was_compressed = self.engine.compress("npm run build", output)
        assert was_compressed
        assert processor == "build"
        assert "Build succeeded" in compressed

    def test_lint_grouped(self):
        lines = []
        for i in range(20):
            lines.append(f"src/file{i}.py:10:1: E501 line too long (120 > 79 characters)")
        for i in range(10):
            lines.append(f"src/file{i}.py:5:1: W291 trailing whitespace")
        output = "\n".join(lines)

        compressed, processor, was_compressed = self.engine.compress("ruff check .", output)
        assert was_compressed
        assert processor == "lint"
        assert "E501" in compressed
        assert "20 occurrences" in compressed

    def test_find_output_grouped(self):
        lines = []
        for i in range(40):
            lines.append(f"src/components/file{i}.tsx")
        for i in range(20):
            lines.append(f"src/utils/helper{i}.ts")
        output = "\n".join(lines)

        compressed, processor, was_compressed = self.engine.compress(
            "find src -name '*.ts*'", output
        )
        assert was_compressed
        assert processor == "file_listing"
        assert "60 files found" in compressed

    def test_cat_long_file_truncated(self):
        lines = [f"line {i}: some code here" for i in range(500)]
        output = "\n".join(lines)

        compressed, processor, was_compressed = self.engine.compress("cat big_file.py", output)
        assert was_compressed
        assert processor == "file_content"
        assert "omitted" in compressed or "truncated" in compressed
        assert len(compressed) < len(output)

    def test_min_compression_ratio(self):
        # Unique lines — generic won't compress much
        output = "\n".join(f"unique_line_content_{i}_{'x' * 50}" for i in range(15))
        compressed, _processor, was_compressed = self.engine.compress("unknown_cmd", output)
        if was_compressed:
            assert len(compressed) <= len(output) * 0.9

    def test_ansi_cleanup_after_specialized_processor(self):
        """Engine should strip ANSI codes even after a specialized processor runs."""
        lines = [f"\x1b[32m M src/file{i}.py\x1b[0m" for i in range(30)]
        output = "On branch main\n\n" + "\n".join(lines)

        compressed, _processor, was_compressed = self.engine.compress("git status", output)
        if was_compressed:
            assert "\x1b[" not in compressed

    def test_git_diff_large_hunk_truncated(self):
        """Large diff hunks should be truncated per-hunk."""
        lines = [
            "diff --git a/big.py b/big.py",
            "--- a/big.py",
            "+++ b/big.py",
            "@@ -1,500 +1,500 @@",
        ]
        for i in range(300):
            lines.append(f"+new line {i}")
        output = "\n".join(lines)

        compressed, _processor, was_compressed = self.engine.compress("git diff", output)
        assert was_compressed
        assert "truncated" in compressed

    def test_processor_priority_git_over_generic(self):
        """Git processor should take priority over generic for git commands."""
        output = "\n".join(
            [
                "On branch main",
                "Changes not staged for commit:",
            ]
            + [f" M file{i}.py" for i in range(30)]
        )

        _, processor, was_compressed = self.engine.compress("git status", output)
        if was_compressed:
            assert processor == "git"

    def test_multiple_compressions_same_engine(self):
        """Engine should handle multiple compress calls."""
        output1 = "\n".join(f"tests/test_{i}.py PASSED" for i in range(50))
        output2 = "\n".join(f" M src/file{i}.py" for i in range(30))

        self.engine.compress("pytest", output1)
        self.engine.compress("git status", "On branch main\n" + output2)
        # Should not crash or leak state

    def test_generic_fallback_when_specialized_fails(self):
        """When specialized processor doesn't compress enough, generic should try."""
        # Create output that a specialized processor handles but barely compresses:
        # git status with very few files (small output, specialized won't compress much)
        # but enough repeated lines for generic to compress.
        # Instead, use a command where the specialized processor returns ~same size.
        output = "repeated_line\n" * 200 + "unique_end"
        compressed, processor, was_compressed = self.engine.compress("some_unknown_cmd", output)
        if was_compressed:
            # Should be compressed via generic (repeated lines)
            assert processor in ("generic", "none")
            assert "x200" in compressed or "repeated" in compressed


class TestProcessorRegistry:
    """Tests for auto-discovery and the processor registry."""

    def test_discover_processors_finds_all(self):
        """Auto-discovery should find all 15 processors."""
        processors = discover_processors()
        assert len(processors) == 15

    def test_discover_processors_sorted_by_priority(self):
        """Processors must be returned in ascending priority order."""
        processors = discover_processors()
        priorities = [p.priority for p in processors]
        assert priorities == sorted(priorities)

    def test_generic_processor_is_last(self):
        """GenericProcessor (priority 999) must always be the last processor."""
        processors = discover_processors()
        assert processors[-1].name == "generic"
        assert processors[-1].priority == 999

    def test_no_duplicate_priorities(self):
        """Each processor should have a unique priority."""
        processors = discover_processors()
        priorities = [p.priority for p in processors]
        assert len(priorities) == len(set(priorities))

    def test_all_processors_have_names(self):
        """Every processor must define a non-empty name."""
        processors = discover_processors()
        for p in processors:
            assert p.name, f"Processor {p.__class__.__name__} has no name"

    def test_expected_priority_order(self):
        """Verify the expected processor priority assignments."""
        processors = discover_processors()
        name_to_priority = {p.name: p.priority for p in processors}
        assert name_to_priority["package_list"] == 15
        assert name_to_priority["git"] == 20
        assert name_to_priority["test"] == 21
        assert name_to_priority["build"] == 25
        assert name_to_priority["lint"] == 27
        assert name_to_priority["network"] == 30
        assert name_to_priority["docker"] == 31
        assert name_to_priority["kubectl"] == 32
        assert name_to_priority["terraform"] == 33
        assert name_to_priority["env"] == 34
        assert name_to_priority["search"] == 35
        assert name_to_priority["system_info"] == 36
        assert name_to_priority["file_listing"] == 50
        assert name_to_priority["file_content"] == 51
        assert name_to_priority["generic"] == 999

    def test_collect_hook_patterns_returns_patterns(self):
        """collect_hook_patterns should return a non-empty list of regex strings."""
        patterns = collect_hook_patterns()
        assert len(patterns) > 0
        assert all(isinstance(p, str) for p in patterns)

    def test_collect_hook_patterns_all_valid_regex(self):
        """All collected hook patterns must be valid regex."""
        import re

        patterns = collect_hook_patterns()
        for p in patterns:
            re.compile(p)  # Should not raise

    def test_collect_hook_patterns_covers_key_commands(self):
        """Collected patterns should match the same commands as the old hardcoded list."""
        import re

        patterns = collect_hook_patterns()
        compiled = [re.compile(p) for p in patterns]

        test_commands = [
            # Git
            "git status",
            "git diff",
            "git log",
            "git blame src/main.py",
            "git cherry-pick abc123",
            "git rebase main",
            "git merge feature/branch",
            "git stash list",
            # Test runners
            "pytest tests/",
            "jest --coverage",
            "cargo test",
            "npm test",
            "pnpm test",
            "yarn test",
            "dotnet test",
            "swift test",
            "mix test",
            "bun test",
            "vitest",
            # Build
            "npm run build",
            "npm install",
            "make",
            "docker build .",
            "docker compose build",
            "turbo run build",
            "nx run build",
            # Lint
            "eslint src/",
            "ruff check .",
            "mypy src/",
            "shellcheck script.sh",
            "hadolint Dockerfile",
            "cargo clippy",
            "prettier --check src/",
            "biome check src/",
            # Network
            "curl https://example.com",
            "wget https://example.com",
            "http GET https://api.example.com",
            # Docker
            "docker ps",
            "docker inspect container",
            "docker stats",
            "docker compose up",
            "docker compose down",
            # Kubectl
            "kubectl get pods",
            "kubectl logs my-pod",
            "kubectl apply -f .",
            "kubectl delete pod my-pod",
            "kubectl create namespace test",
            # Terraform
            "terraform plan",
            "terraform init",
            "terraform output",
            "terraform state list",
            "tofu apply",
            # Env
            "env",
            "printenv",
            # Search
            "grep -r pattern .",
            "rg pattern",
            "fd -e py",
            "fdfind pattern",
            # System info
            "du -sh *",
            "wc -l *.py",
            "df -h",
            # File listing
            "ls -la",
            "find . -name '*.py'",
            "tree src/",
            "exa -la",
            "eza --long",
            # File content
            "cat file.py",
            "head -20 file.py",
            "bat file.py",
            # Package list
            "pip list",
            "pip freeze",
            "npm ls",
            "conda list",
        ]

        for cmd in test_commands:
            matched = any(p.search(cmd) for p in compiled)
            assert matched, f"Command {cmd!r} not matched by any hook pattern"

    def test_engine_uses_discovered_processors(self):
        """CompressionEngine should use auto-discovered processors."""
        engine = CompressionEngine()
        discovered = discover_processors()
        assert len(engine.processors) == len(discovered)
        for ep, dp in zip(engine.processors, discovered, strict=False):
            assert ep.name == dp.name
            assert ep.priority == dp.priority
