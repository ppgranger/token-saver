"""Precision tests: verify no critical information is lost during compression.

These tests simulate real-world outputs and validate that all actionable
information survives compression.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import CompressionEngine


class TestGitPrecision:
    """Ensure git compression preserves all actionable information."""

    def setup_method(self):
        self.engine = CompressionEngine()

    def test_status_long_format_preserves_untracked(self):
        """Long-format git status must preserve untracked files."""
        output = "\n".join(
            [
                "On branch feature/auth",
                "Changes not staged for commit:",
                '  (use "git add <file>..." to update what will be committed)',
                "\tmodified:   src/auth.py",
                "\tmodified:   src/models.py",
                "",
                "Untracked files:",
                '  (use "git add <file>..." to include in what will be committed)',
                "\tsrc/new_handler.py",
                "\ttests/test_auth_new.py",
                "",
                "no changes added to commit",
            ]
        )
        compressed, _, _was_compressed = self.engine.compress("git status", output)
        # All files must be present
        assert "auth.py" in compressed
        assert "models.py" in compressed
        assert "new_handler.py" in compressed
        assert "test_auth_new.py" in compressed
        assert "feature/auth" in compressed
        # Untracked count correct
        assert "?:2" in compressed

    def test_status_short_format_preserves_all(self):
        output = " M src/a.py\n M src/b.py\n D src/c.py\n?? src/d.py\nA  src/e.py\n" * 5
        compressed, _, _ = self.engine.compress("git status -s", output)
        # All status codes must appear
        for code in ["M", "D", "?", "A"]:
            assert code in compressed

    def test_diff_preserves_all_filenames(self):
        """All modified files must appear in compressed diff."""
        files = ["auth.py", "models.py", "views.py", "urls.py", "settings.py"]
        lines = []
        for f in files:
            lines.extend(
                [
                    f"diff --git a/src/{f} b/src/{f}",
                    f"--- a/src/{f}",
                    f"+++ b/src/{f}",
                    "@@ -1,3 +1,4 @@",
                    " existing line",
                    "+new line",
                    " existing line",
                ]
            )
        output = "\n".join(lines)
        compressed, _, _ = self.engine.compress("git diff", output)
        for f in files:
            assert f in compressed, f"File {f} missing from compressed diff"

    def test_diff_preserves_all_changes(self):
        """All +/- lines must survive context reduction."""
        lines = [
            "diff --git a/file.py b/file.py",
            "@@ -1,20 +1,22 @@",
        ]
        # 8 context lines
        for i in range(8):
            lines.append(f" unchanged_{i}")
        # Changes
        lines.append("-removed_line_alpha")
        lines.append("+added_line_alpha")
        # 8 more context lines
        for i in range(8):
            lines.append(f" middle_{i}")
        # More changes
        lines.append("-removed_line_beta")
        lines.append("+added_line_beta")
        # 8 trailing context
        for i in range(8):
            lines.append(f" trailing_{i}")

        output = "\n".join(lines)
        compressed, _, _ = self.engine.compress("git diff", output)
        # All actual changes must be preserved
        assert "-removed_line_alpha" in compressed
        assert "+added_line_alpha" in compressed
        assert "-removed_line_beta" in compressed
        assert "+added_line_beta" in compressed
        # But not all context lines
        assert "unchanged_0" not in compressed  # too far from change

    def test_diff_stat_preserves_filenames_and_summary(self):
        """git diff --stat must keep all filenames and the summary."""
        output = "\n".join(
            [
                " src/auth.py    | 15 +++++++++------",
                " src/models.py  |  3 +++",
                " src/views.py   |  8 ++------",
                " 3 files changed, 14 insertions(+), 12 deletions(-)",
            ]
        )
        compressed, _, _ = self.engine.compress("git diff --stat", output)
        assert "auth.py" in compressed
        assert "models.py" in compressed
        assert "views.py" in compressed
        assert "3 files changed" in compressed

    def test_log_preserves_commit_hashes(self):
        """Commit hashes must survive compression."""
        entries = []
        hashes = []
        for i in range(25):
            h = f"{i:08x}" + "a" * 32
            hashes.append(h[:8])
            entries.extend(
                [
                    f"commit {h}",
                    "Author: Dev <d@d.com>",
                    f"Date: Jan {i + 1}",
                    "",
                    f"    msg {i}",
                    "",
                ]
            )
        output = "\n".join(entries)
        compressed, _, _ = self.engine.compress("git log", output)
        # First 20 hashes must be present
        for h in hashes[:20]:
            assert h in compressed, f"Hash {h} missing"

    def test_push_preserves_branch_ref(self):
        output = "\n".join(
            [
                "Counting objects: 100% (5/5), done.",
                "Compressing objects: 100% (3/3), done.",
                "Writing objects: 100% (3/3), 1.2 KiB | 1.2 MiB/s, done.",
                "remote: Resolving deltas: 100% (2/2), done.",
                "To github.com:user/repo.git",
                "   abc1234..def5678  feature/auth -> feature/auth",
            ]
        )
        compressed, _, _ = self.engine.compress("git push origin feature/auth", output)
        assert "feature/auth" in compressed
        assert "abc1234" in compressed or "def5678" in compressed


class TestTestPrecision:
    """Ensure test compression preserves all failure details."""

    def setup_method(self):
        self.engine = CompressionEngine()

    def test_pytest_failure_stack_preserved(self):
        output = "\n".join(
            [
                "=" * 60 + " test session starts " + "=" * 60,
                "platform darwin -- Python 3.12.0",
                "collected 100 items",
            ]
            + [f"tests/test_{i}.py::test_func PASSED" for i in range(97)]
            + [
                "tests/test_db.py::test_migration FAILED",
                "",
                "=" * 60 + " FAILURES " + "=" * 60,
                "_____ test_migration _____",
                "",
                "    def test_migration():",
                "        db = get_db()",
                ">       db.migrate('v2')",
                "",
                "tests/test_db.py:42",
                "",
                "E       MigrationError: column 'email' already exists",
                "E       ",
                "E       During handling of the above exception:",
                "E       ",
                "E       RuntimeError: migration failed at step 3",
                "",
                "=" * 60 + " short test summary info " + "=" * 60,
                "FAILED tests/test_db.py::test_migration - MigrationError",
                "=" * 60 + " 1 failed, 97 passed in 12.3s " + "=" * 60,
            ]
        )
        compressed, _, was_compressed = self.engine.compress("pytest", output)
        assert was_compressed
        # All failure info preserved
        assert "MigrationError" in compressed
        assert "column 'email' already exists" in compressed
        assert "migration failed at step 3" in compressed
        assert "test_db.py" in compressed
        assert "97 tests passed" in compressed
        assert "1 failed" in compressed
        # Noise removed
        assert "platform darwin" not in compressed

    def test_all_failures_kept_when_multiple(self):
        output = "\n".join(
            [
                "=" * 40 + " test session starts " + "=" * 40,
                "tests/a.py::test1 PASSED",
                "tests/b.py::test2 FAILED",
                "tests/c.py::test3 FAILED",
                "",
                "=" * 40 + " FAILURES " + "=" * 40,
                "_____ test2 _____",
                ">   assert x == 1",
                "E   assert 2 == 1",
                "tests/b.py:10: AssertionError",
                "_____ test3 _____",
                ">   raise ValueError('bad')",
                "E   ValueError: bad",
                "tests/c.py:20: ValueError",
                "=" * 40 + " 2 failed, 1 passed " + "=" * 40,
            ]
        )
        compressed, _, _ = self.engine.compress("pytest", output)
        assert "assert 2 == 1" in compressed
        assert "ValueError: bad" in compressed
        assert "b.py:10" in compressed
        assert "c.py:20" in compressed


class TestBuildPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_all_errors_preserved(self):
        output = "\n".join(
            [
                "Compiling project...",
            ]
            + [f"  Compiling dep-{i}" for i in range(50)]
            + [
                "error: src/main.rs:10:5: mismatched types",
                "  expected u32, found &str",
                "",
                "error: src/lib.rs:25:1: unused import",
                "  use std::io;",
                "",
                "error: aborting due to 2 previous errors",
            ]
        )
        compressed, _, was_compressed = self.engine.compress("cargo build", output)
        assert was_compressed
        assert "mismatched types" in compressed
        assert "unused import" in compressed
        assert "main.rs" in compressed
        assert "lib.rs" in compressed

    def test_success_build_preserves_output_info(self):
        output = "\n".join(
            [
                "  Installing lodash@4.17.21",
                "  Installing react@18.2.0",
            ]
            * 20
            + [
                "Build completed successfully in 15.3s",
                "Output: dist/bundle.js (245 KB gzipped)",
            ]
        )
        compressed, _, was_compressed = self.engine.compress("npm run build", output)
        assert was_compressed
        assert "Build succeeded" in compressed
        assert "245 KB" in compressed or "gzip" in compressed

    def test_errors_mentioning_step_keywords_preserved(self):
        """Errors containing 'Resolution step' or 'Fetch step' must not be stripped."""
        output = "\n".join(
            [f"  Resolving dep-{i}" for i in range(50)]
            + [
                "error: Resolution step failed: ETIMEDOUT",
                "  at NetworkManager.fetch (node_modules/yarn/lib/cli.js:123)",
                "",
                "error: Fetch step encountered a certificate error",
                "  UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
            ]
        )
        compressed, _, was_compressed = self.engine.compress("yarn install", output)
        assert was_compressed
        assert "Resolution step failed" in compressed
        assert "ETIMEDOUT" in compressed
        assert "Fetch step encountered" in compressed
        assert "UNABLE_TO_GET_ISSUER_CERT_LOCALLY" in compressed


class TestLintPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_eslint_block_format_grouped(self):
        eslint = ""
        for i in range(10):
            eslint += f"/src/file{i}.ts\n"
            eslint += f"  10:{i}  error  Unexpected var  no-var\n"
            eslint += f"  20:{i}  error  Missing return  consistent-return\n\n"
        eslint += "20 problems (20 errors, 0 warnings)"
        compressed, _, was_compressed = self.engine.compress("eslint src/", eslint)
        assert was_compressed
        assert "no-var" in compressed
        assert "consistent-return" in compressed
        assert "20 issues across 2 rules" in compressed
        # Examples shown
        assert "Unexpected var" in compressed

    def test_ruff_all_rules_visible(self):
        rules = ["E501", "F401", "W291", "E302"]
        lines = []
        for rule in rules:
            for i in range(5):
                lines.append(f"src/f{i}.py:1:1: {rule} some message")
        output = "\n".join(lines)
        compressed, _, was_compressed = self.engine.compress("ruff check .", output)
        assert was_compressed
        for rule in rules:
            assert rule in compressed, f"Rule {rule} missing"


class TestDockerPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_docker_build_preserves_steps_and_result(self):
        output = "\n".join(
            [
                "Sending build context to Docker daemon  5MB",
                "Step 1/5 : FROM python:3.12",
                " ---> abc123",
                "Step 2/5 : COPY requirements.txt .",
                "Running in def456",
                "Removing intermediate container def456",
                "Step 3/5 : RUN pip install -r requirements.txt",
                "Downloading numpy-1.26.0",
                "Step 4/5 : COPY . .",
                'Step 5/5 : CMD ["python", "app.py"]',
                "Successfully built abc123",
                "Successfully tagged myapp:1.0",
            ]
        )
        compressed, _, was_compressed = self.engine.compress("docker build -t myapp:1.0 .", output)
        assert was_compressed
        assert "Step 1/5" in compressed
        assert "Step 5/5" in compressed
        assert "Successfully tagged" in compressed
        assert "Removing intermediate" not in compressed


class TestPytestWarningPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_warnings_type_visible(self):
        """Warning types should be visible after compression."""
        output = "\n".join(
            [
                "=" * 40 + " test session starts " + "=" * 40,
            ]
            + [f"tests/test_{i}.py::test PASSED" for i in range(50)]
            + [
                "=" * 40 + " warnings summary " + "=" * 40,
            ]
            + [f"  /lib/pkg.py:{i}: DeprecationWarning: old_func() deprecated" for i in range(20)]
            + [f"  /lib/other.py:{i}: UserWarning: check something" for i in range(5)]
            + [
                "-- Docs: https://docs.pytest.org",
                "=" * 40 + " 50 passed, 25 warnings " + "=" * 40,
            ]
        )
        compressed, _, was_compressed = self.engine.compress("pytest", output)
        assert was_compressed
        assert "50 tests passed" in compressed
        assert "DeprecationWarning" in compressed
        assert "50 passed" in compressed


class TestCurlPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_curl_verbose_preserves_status_and_body(self):
        """HTTP status code and response body must survive compression."""
        output = "\n".join(
            [
                "* Trying 10.0.0.1:443...",
                "* Connected to api.example.com (10.0.0.1) port 443",
                "* TLSv1.3 (OUT), TLS handshake, Client hello (1):",
                "* TLSv1.3 (IN), TLS handshake, Server hello (2):",
                "* SSL connection using TLSv1.3",
                "> POST /api/users HTTP/2",
                "> Host: api.example.com",
                "> Content-Type: application/json",
                "< HTTP/2 201",
                "< content-type: application/json",
                "< location: /api/users/42",
                "< date: Mon, 01 Jan 2025 12:00:00 GMT",
                "< server: nginx",
                "<",
                '{"id": 42, "name": "test"}',
                "* Connection #0 left intact",
            ]
        )
        compressed, _, was_compressed = self.engine.compress(
            "curl -v https://api.example.com/api/users", output
        )
        assert was_compressed
        assert "HTTP/2 201" in compressed
        assert "POST /api/users" in compressed
        assert '{"id": 42' in compressed
        assert "location: /api/users/42" in compressed
        assert "TLSv1.3" not in compressed


class TestDockerPsPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_docker_ps_preserves_unhealthy_containers(self):
        header = (
            "CONTAINER ID   IMAGE          COMMAND"
            "       CREATED       STATUS"
            "                  PORTS     NAMES"
        )
        entries = []
        for i in range(15):
            entries.append(
                f'abc{i:010d}   nginx:latest   "nginx"'
                f"       {i}h ago      Up {i} hours"
                f"             80/tcp    web-{i}"
            )
        entries.append(
            'def0000000000   myapp:latest   "python"'
            "      2h ago       Exited (1) 30 min ago"
            "             crashed-app"
        )
        output = "\n".join([header, *entries])
        compressed, _, was_compressed = self.engine.compress("docker ps -a", output)
        assert was_compressed
        assert "crashed-app" in compressed
        assert "Exited" in compressed


class TestSearchPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_grep_preserves_all_matching_files(self):
        """All files with matches should be visible."""
        lines = []
        files = [f"src/module{i}.py" for i in range(25)]
        for f in files:
            for j in range(4):
                lines.append(f"{f}:{j + 1}:import pattern_here line {j}")
        output = "\n".join(lines)
        compressed, _, was_compressed = self.engine.compress("grep -r pattern_here .", output)
        assert was_compressed
        assert "100 matches" in compressed
        # All files should be represented
        for f in files[:20]:  # First 20 shown
            assert f in compressed


class TestEnvPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_env_never_leaks_secrets(self):
        """Sensitive values must be redacted."""
        lines = [
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "DATABASE_PASSWORD=p4$$w0rd_super_secret",
            "GITHUB_TOKEN=ghp_1234567890abcdefghijklmnop",
            "NORMAL_VAR=hello_world",
            "TERM=xterm-256color",
            "SHELL=/bin/zsh",
            "USER=developer",
            "HOME=/home/developer",
            "LANG=en_US.UTF-8",
            "LC_ALL=en_US.UTF-8",
            "LC_CTYPE=UTF-8",
            "SSH_AUTH_SOCK=/tmp/ssh-agent.sock",
            "SSH_AGENT_PID=12345",
            "DISPLAY=:0",
            "XDG_SESSION_TYPE=wayland",
            "XDG_RUNTIME_DIR=/run/user/1000",
            "COLORTERM=truecolor",
            "TERM_PROGRAM=iTerm2",
            "SHLVL=2",
            "OLDPWD=/home/developer/projects",
            "LOGNAME=developer",
            "HISTSIZE=50000",
            "HISTFILE=/home/developer/.bash_history",
            "LSCOLORS=ExGxBxDxCxEgEdxbxgxcxd",
        ] + [f"APP_VAR_{i}=value_{i}" for i in range(10)]
        output = "\n".join(lines)
        compressed, _, was_compressed = self.engine.compress("env", output)
        assert was_compressed
        # Secrets must NOT appear
        assert "wJalrXUtnFEMI" not in compressed
        assert "p4$$w0rd" not in compressed
        assert "ghp_1234567890" not in compressed
        # But keys are visible
        assert "AWS_SECRET_ACCESS_KEY" in compressed
        assert "DATABASE_PASSWORD" in compressed
        assert "GITHUB_TOKEN" in compressed


class TestKubectlPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_kubectl_get_pods_preserves_failing_pods(self):
        header = "NAME                    READY   STATUS             RESTARTS   AGE"
        entries = [
            f"healthy-{i:03d}             1/1     Running            0          {i}h"
            for i in range(25)
        ]
        entries.append("broken-pod              0/1     CrashLoopBackOff   15         1h")
        entries.append("pending-pod             0/1     Pending            0          30m")
        output = "\n".join([header, *entries])
        compressed, _, was_compressed = self.engine.compress("kubectl get pods", output)
        assert was_compressed
        assert "CrashLoopBackOff" in compressed
        assert "Pending" in compressed
        assert "broken-pod" in compressed
        assert "pending-pod" in compressed


class TestTerraformPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_terraform_plan_preserves_summary_and_changes(self):
        output = "\n".join(
            [
                "Initializing the backend...",
                "Initializing provider plugins...",
                "- Installing hashicorp/aws v5.0.0...",
                "- Installed hashicorp/aws v5.0.0",
                "",
                "# aws_instance.web will be created",
                '  + resource "aws_instance" "web" {',
                '      + ami           = "ami-12345678"',
                '      + instance_type = "t3.micro"',
                "      + id            = (known after apply)",
                "    }",
                "",
                "# aws_s3_bucket.data will be destroyed",
                '  - resource "aws_s3_bucket" "data" {',
                "    }",
                "",
                "Plan: 1 to add, 0 to change, 1 to destroy.",
            ]
            + [""] * 20
        )
        compressed, _, was_compressed = self.engine.compress("terraform plan", output)
        assert was_compressed
        assert "aws_instance.web" in compressed
        assert "aws_s3_bucket.data" in compressed
        assert "ami-12345678" in compressed
        assert "Plan: 1 to add" in compressed
        assert "(known after apply)" in compressed
        assert "Initializing" not in compressed


class TestPackageListPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_npm_ls_preserves_unmet_dependencies(self):
        lines = ["my-project@1.0.0 /home/user/project"]
        for i in range(30):
            lines.append(f"├── package-{i}@{i}.0.0")
            lines.append(f"│   ├── sub-dep-{i}@0.1.0")
        lines.append("├── UNMET DEPENDENCY critical-package@^2.0.0")
        output = "\n".join(lines)
        compressed, _, was_compressed = self.engine.compress("npm ls", output)
        assert was_compressed
        assert "UNMET" in compressed
        assert "critical-package" in compressed

    def test_pip_list_routed_to_package_processor_not_build(self):
        """pip list must NOT produce 'Build succeeded.' output."""
        lines = ["Package    Version", "---------- -------"]
        for i in range(50):
            lines.append(f"package-{i:03d}  {i}.0.0")
        output = "\n".join(lines)
        compressed, processor, was_compressed = self.engine.compress("pip list", output)
        assert was_compressed
        assert processor == "package_list"
        assert "Build succeeded" not in compressed
        assert "packages installed" in compressed


class TestGenericPrecision:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_unique_lines_never_lost(self):
        """Unique content should never be silently dropped."""
        unique_lines = [f"IMPORTANT_DATA_{i}: value_{i}" for i in range(100)]
        output = "\n".join(unique_lines)
        compressed, _, was_compressed = self.engine.compress("unknown_cmd", output)
        # If compressed, all unique lines should still be there
        # (generic only deduplicates identical lines)
        if was_compressed:
            for line in unique_lines:
                assert line in compressed, f"Lost unique line: {line}"
        else:
            assert compressed == output

    def test_short_output_never_modified(self):
        """Output below threshold must pass through untouched."""
        output = "Result: 42\nDone."
        compressed, _, was_compressed = self.engine.compress("any_cmd", output)
        assert not was_compressed
        assert compressed == output
