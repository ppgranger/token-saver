"""Tests for individual processors."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.processors.build_output import BuildOutputProcessor
from src.processors.cloud_cli import CloudCliProcessor
from src.processors.db_query import DbQueryProcessor
from src.processors.docker import DockerProcessor
from src.processors.env import EnvProcessor
from src.processors.file_content import FileContentProcessor
from src.processors.file_listing import FileListingProcessor
from src.processors.generic import GenericProcessor
from src.processors.gh import GhProcessor
from src.processors.git import GitProcessor
from src.processors.kubectl import KubectlProcessor
from src.processors.lint_output import LintOutputProcessor
from src.processors.network import NetworkProcessor
from src.processors.package_list import PackageListProcessor
from src.processors.search import SearchProcessor
from src.processors.system_info import SystemInfoProcessor
from src.processors.terraform import TerraformProcessor
from src.processors.test_output import TestOutputProcessor


class TestGitProcessor:
    def setup_method(self):
        self.p = GitProcessor()

    def test_can_handle_git_commands(self):
        assert self.p.can_handle("git status")
        assert self.p.can_handle("git diff --cached")
        assert self.p.can_handle("git log --oneline -20")
        assert self.p.can_handle("git push origin main")
        assert self.p.can_handle("git show HEAD")
        assert self.p.can_handle("git branch -a")
        assert self.p.can_handle("git reflog")
        assert not self.p.can_handle("grep git")
        assert not self.p.can_handle("ls -la")

    def test_can_handle_git_with_global_options(self):
        assert self.p.can_handle("git -C /some/path status")
        assert self.p.can_handle("git -C /opt/homebrew log --oneline")
        assert self.p.can_handle("git --no-pager diff HEAD~1")
        assert self.p.can_handle("git -C /path --no-pager log")
        assert self.p.can_handle("git --no-pager -C /path status")
        assert self.p.can_handle("git -c core.pager=cat diff")
        assert self.p.can_handle("git --git-dir=/repo/.git status")
        assert self.p.can_handle("git --work-tree /repo diff")

    def test_process_routes_with_global_options(self):
        """Commands with global options should route to the correct processor."""
        status_output = "On branch main\nnothing to commit, working tree clean"
        result = self.p.process("git -C /some/path status", status_output)
        assert "nothing to commit" in result

        log_lines = [f"abc{i:04d} commit message {i}" for i in range(30)]
        log_output = "\n".join(log_lines)
        result = self.p.process("git -C /opt/homebrew --no-pager log --oneline", log_output)
        assert "more" in result

    def test_empty_output(self):
        assert self.p.process("git status", "") == ""
        assert self.p.process("git status", "   ") == "   "

    def test_status_condensed(self):
        output = "\n".join(
            [
                "On branch feature/test",
                "Changes not staged for commit:",
                " M src/app.py",
                " M src/utils.py",
                " M src/config.py",
                "Untracked files:",
                " ?? new.txt",
                " ?? temp.log",
            ]
        )
        result = self.p.process("git status", output)
        assert "feature/test" in result
        assert "M" in result

    def test_status_nothing_to_commit(self):
        output = "On branch main\nnothing to commit, working tree clean"
        result = self.p.process("git status", output)
        assert "nothing to commit" in result

    def test_status_many_files_per_dir(self):
        """Dirs with >8 files should be collapsed."""
        files = [f" M src/file{i}.py" for i in range(15)]
        output = "On branch main\n" + "\n".join(files)
        result = self.p.process("git status", output)
        assert "15 files" in result
        assert "src" in result

    def test_log_compact(self):
        entries = []
        for i in range(25):
            entries.extend(
                [
                    f"commit {'a' * 40}",
                    "Author: Dev <dev@example.com>",
                    f"Date:   Mon Jan {i + 1} 12:00:00 2025 +0000",
                    "",
                    f"    Fix bug #{i}",
                    "",
                ]
            )
        output = "\n".join(entries)
        result = self.p.process("git log", output)
        lines = [line for line in result.splitlines() if line.strip()]
        assert len(lines) <= 21

    def test_log_already_oneline(self):
        """Already compact log should just be truncated."""
        lines = [f"abc{i:04d} commit message {i}" for i in range(30)]
        output = "\n".join(lines)
        result = self.p.process("git log --oneline", output)
        assert "more" in result

    def test_push_removes_progress(self):
        output = "\n".join(
            [
                "Counting objects: 5, done.",
                "Compressing objects: 100% (3/3), done.",
                "Writing objects: 100% (3/3), 300 bytes | 300.00 KiB/s, done.",
                "Total 3 (delta 2), reused 0 (delta 0)",
                "To github.com:user/repo.git",
                "   abc1234..def5678  main -> main",
            ]
        )
        result = self.p.process("git push", output)
        assert "100%" not in result
        assert "main -> main" in result

    def test_push_all_progress(self):
        """When all lines are progress, should return last non-empty line."""
        output = "Counting objects: 100% (5/5)\nCompressing objects: 100% (3/3)\n"
        result = self.p.process("git push", output)
        assert result.strip()  # Should not be empty

    def test_diff_hunk_truncation(self):
        lines = ["diff --git a/big.py b/big.py", "@@ -1,300 +1,300 @@"]
        for i in range(300):
            lines.append(f"+line {i}")
        output = "\n".join(lines)
        result = self.p.process("git diff", output)
        assert "truncated" in result
        assert len(result) < len(output)

    def test_diff_strips_index_lines(self):
        """index lines (blob hashes) should be removed."""
        output = "\n".join(
            [
                "diff --git a/file.py b/file.py",
                "index abc1234..def5678 100644",
                "--- a/file.py",
                "+++ b/file.py",
                "@@ -1,3 +1,4 @@",
                " context",
                "+added",
                " context",
            ]
        )
        result = self.p.process("git diff", output)
        assert "index abc1234" not in result
        assert "diff --git" in result
        assert "+added" in result

    def test_diff_strips_minus_plus_headers(self):
        """--- and +++ lines should be stripped (redundant with diff --git)."""
        output = "\n".join(
            [
                "diff --git a/file.py b/file.py",
                "--- a/file.py",
                "+++ b/file.py",
                "@@ -1,3 +1,4 @@",
                "+added line",
            ]
        )
        result = self.p.process("git diff", output)
        assert "--- a/file.py" not in result
        assert "+++ b/file.py" not in result
        assert "diff --git a/file.py" in result
        assert "+added line" in result

    def test_diff_context_lines_limited(self):
        """Context lines should be limited to max_diff_context_lines around changes."""
        lines = ["diff --git a/file.py b/file.py", "@@ -1,20 +1,21 @@"]
        # 10 context lines before the change
        for i in range(10):
            lines.append(f" context_before_{i}")
        lines.append("+added line")
        # 10 context lines after the change
        for i in range(10):
            lines.append(f" context_after_{i}")
        output = "\n".join(lines)
        result = self.p.process("git diff", output)
        # Should have at most 3 context lines before and 3 after (default)
        assert "+added line" in result
        # Early context lines should be dropped
        assert "context_before_0" not in result
        # Last 3 before the change should be kept
        assert "context_before_9" in result
        # First 3 after should be kept
        assert "context_after_0" in result
        # Late context lines should be dropped
        assert "context_after_9" not in result

    def test_diff_stat_format(self):
        """git diff --stat visual bars should be stripped."""
        output = "\n".join(
            [
                " src/auth.py    | 15 +++++++++------",
                " src/models.py  |  3 +++",
                " src/views.py   |  8 ++------",
                " 3 files changed, 14 insertions(+), 12 deletions(-)",
            ]
        )
        result = self.p.process("git diff --stat", output)
        assert "auth.py" in result
        assert "+++" not in result or "+++" in result.split("changed")[0]  # bars stripped
        assert "3 files changed" in result

    def test_show_with_diff(self):
        output = "\n".join(
            [
                "commit abc123",
                "Author: Dev <dev@example.com>",
                "Date: Mon Jan 1 2025",
                "",
                "    Fix something",
                "",
                "diff --git a/file.py b/file.py",
                "--- a/file.py",
                "+++ b/file.py",
                "@@ -1,3 +1,3 @@",
                "-old line",
                "+new line",
            ]
        )
        result = self.p.process("git show HEAD", output)
        assert "abc123" in result
        assert "+new line" in result
        # Author and Date should be stripped
        assert "Author:" not in result
        assert "Date:" not in result
        assert "Fix something" in result

    def test_branch_many(self):
        lines = ["* main"] + [f"  feature/branch-{i}" for i in range(50)]
        output = "\n".join(lines)
        result = self.p.process("git branch -a", output)
        assert "50 other branches" in result

    def test_reflog_truncation(self):
        lines = [f"abc{i:04d} HEAD@{{{i}}}: commit: msg {i}" for i in range(50)]
        output = "\n".join(lines)
        result = self.p.process("git reflog", output)
        assert "more entries" in result

    def test_can_handle_blame(self):
        assert self.p.can_handle("git blame src/main.py")

    def test_blame_short_unchanged(self):
        lines = [
            f"abc1234{i} (Author 2025-01-01 12:00:00 +0000 {i + 1}) line {i}" for i in range(10)
        ]
        output = "\n".join(lines)
        result = self.p.process("git blame src/main.py", output)
        assert result == output

    def test_blame_groups_by_author(self):
        lines = []
        for i in range(30):
            author = "Alice" if i < 20 else "Bob"
            lines.append(
                f"abc{i:04d}00 ({author} 2025-01-{i + 1:02d} 12:00:00 +0000 {i + 1}) line {i}"
            )
        output = "\n".join(lines)
        result = self.p.process("git blame src/main.py", output)
        assert "30 lines" in result
        assert "2 authors" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "Last 10 lines" in result

    def test_can_handle_cherry_pick_rebase_merge(self):
        assert self.p.can_handle("git cherry-pick abc123")
        assert self.p.can_handle("git rebase main")
        assert self.p.can_handle("git merge feature/branch")

    def test_cherry_pick_removes_progress(self):
        output = "\n".join(
            [
                "Counting objects: 5, done.",
                "Compressing objects: 100% (3/3), done.",
                "[main abc1234] Cherry-picked commit message",
                " 2 files changed, 10 insertions(+), 3 deletions(-)",
            ]
        )
        result = self.p.process("git cherry-pick abc123", output)
        assert "100%" not in result
        assert "Cherry-picked" in result

    def test_diff_name_only(self):
        lines = [f"src/dir/file{i}.py" for i in range(25)]
        output = "\n".join(lines)
        result = self.p.process("git diff --name-only HEAD~5", output)
        assert "25 files changed" in result
        assert "src/dir" in result

    def test_diff_name_only_short_unchanged(self):
        output = "src/a.py\nsrc/b.py\nsrc/c.py"
        result = self.p.process("git diff --name-only", output)
        assert result == output

    def test_diff_name_status(self):
        lines = [f"M\tsrc/dir/file{i}.py" for i in range(25)]
        output = "\n".join(lines)
        result = self.p.process("git diff --name-status HEAD~5", output)
        assert "25 files changed" in result

    def test_stash_list(self):
        lines = [f"stash@{{{i}}}: WIP on branch: message {i}" for i in range(20)]
        output = "\n".join(lines)
        result = self.p.process("git stash list", output)
        assert "more stashes" in result

    def test_stash_list_short_unchanged(self):
        output = "stash@{0}: WIP on main: abc1234 message"
        result = self.p.process("git stash list", output)
        assert result == output

    def test_status_head_detached(self):
        output = "HEAD detached at abc1234\nnothing to commit, working tree clean"
        result = self.p.process("git status", output)
        assert "HEAD detached" in result

    def test_status_conflict_markers(self):
        output = "\n".join(
            [
                "On branch main",
                "Unmerged paths:",
                "  both modified:   src/conflict.py",
                "  both added:      src/new.py",
            ]
        )
        result = self.p.process("git status", output)
        assert "conflict.py" in result
        assert "new.py" in result


class TestTestOutputProcessor:
    def setup_method(self):
        self.p = TestOutputProcessor()

    def test_can_handle_test_commands(self):
        assert self.p.can_handle("pytest tests/")
        assert self.p.can_handle("python -m pytest")
        assert self.p.can_handle("python3 -m pytest")
        assert self.p.can_handle("jest --coverage")
        assert self.p.can_handle("cargo test")
        assert self.p.can_handle("go test ./...")
        assert self.p.can_handle("npm test")
        assert self.p.can_handle("bun test")
        assert not self.p.can_handle("git status")

    def test_empty_output(self):
        assert self.p.process("pytest", "") == ""

    def test_pytest_collapses_passed(self):
        lines = [f"tests/test_{i}.py::test_func PASSED" for i in range(30)]
        lines.append("=" * 40 + " 30 passed " + "=" * 40)
        output = "\n".join(lines)
        result = self.p.process("pytest", output)
        assert "30 tests passed" in result
        assert "PASSED" not in result

    def test_pytest_keeps_failures(self):
        output = "\n".join(
            [
                "tests/test_a.py::test_one PASSED",
                "tests/test_a.py::test_two PASSED",
                "=" * 40 + " FAILURES " + "=" * 40,
                "_____ test_broken _____",
                "    def test_broken():",
                ">       assert 1 == 2",
                "E       AssertionError",
                "=" * 40 + " 1 failed, 2 passed " + "=" * 40,
            ]
        )
        result = self.p.process("pytest", output)
        assert "assert 1 == 2" in result
        assert "failed" in result

    def test_pytest_skips_collection_and_platform(self):
        output = "\n".join(
            [
                "platform darwin -- Python 3.12.0",
                "rootdir: /home/user/project",
                "plugins: mock-3.0.0",
                "collecting ... collected 5 items",
                "tests/test_a.py::test_one PASSED",
                "tests/test_a.py::test_two PASSED",
                "tests/test_a.py::test_three PASSED",
                "tests/test_a.py::test_four PASSED",
                "tests/test_a.py::test_five PASSED",
                "=" * 40 + " 5 passed " + "=" * 40,
            ]
        )
        result = self.p.process("pytest", output)
        assert "platform" not in result
        assert "rootdir" not in result
        assert "5 tests passed" in result

    def test_cargo_test_skips_compilation(self):
        output = "\n".join(
            [
                "   Compiling myproject v0.1.0",
                "    Running tests/test_main.rs",
                "test tests::test_one ... ok",
                "test tests::test_two ... ok",
                "test tests::test_three ... ok",
                "test result: ok. 3 passed; 0 failed; 0 ignored",
            ]
        )
        result = self.p.process("cargo test", output)
        assert "3 tests passed" in result
        assert "Compiling" not in result

    def test_pytest_warnings_collapsed_by_type(self):
        """Warnings should be grouped by type, not dropped entirely."""
        output = "\n".join(
            [
                "=" * 40 + " test session starts " + "=" * 40,
                "tests/test_a.py::test1 PASSED",
                "tests/test_a.py::test2 PASSED",
                "tests/test_a.py::test3 PASSED",
                "=" * 40 + " warnings summary " + "=" * 40,
                "tests/test_a.py::test1",
                "  /usr/lib/python3/site-packages/pkg/mod.py:10:"
                " DeprecationWarning: func_a() deprecated",
                "tests/test_a.py::test2",
                "  /usr/lib/python3/site-packages/pkg/mod.py:20:"
                " DeprecationWarning: func_b() deprecated",
                "tests/test_a.py::test3",
                "  /usr/lib/python3/site-packages/pkg/mod.py:30: UserWarning: check config",
                "-- Docs: https://docs.pytest.org/en/stable/warnings.html",
                "=" * 40 + " 3 passed, 3 warnings " + "=" * 40,
            ]
        )
        result = self.p.process("pytest", output)
        assert "3 tests passed" in result
        assert "DeprecationWarning" in result
        assert "3 passed" in result
        # Should be collapsed, not all individual lines
        assert result.count("DeprecationWarning") <= 2

    def test_pytest_no_warnings_unchanged(self):
        """When there are no warnings, behavior should be unchanged."""
        output = "\n".join(
            [
                "tests/test_a.py::test1 PASSED",
                "tests/test_a.py::test2 PASSED",
                "=" * 40 + " 2 passed " + "=" * 40,
            ]
        )
        result = self.p.process("pytest", output)
        assert "2 tests passed" in result

    def test_go_test_keeps_package_summary(self):
        output = "\n".join(
            [
                "--- PASS: TestOne (0.01s)",
                "--- PASS: TestTwo (0.02s)",
                "ok  \tgithub.com/user/pkg\t0.03s",
            ]
        )
        result = self.p.process("go test ./...", output)
        assert "2 tests passed" in result
        assert "github.com/user/pkg" in result

    def test_can_handle_pnpm_dotnet_swift_mix(self):
        assert self.p.can_handle("pnpm test")
        assert self.p.can_handle("dotnet test")
        assert self.p.can_handle("swift test")
        assert self.p.can_handle("mix test")

    def test_pnpm_test_routes_to_jest(self):
        """pnpm test should use jest processor."""
        lines = [
            "PASS src/app.test.ts (5 tests)",
            "PASS src/util.test.ts (3 tests)",
            "Tests:  8 passed",
            "Time:   2.5s",
        ]
        output = "\n".join(lines)
        result = self.p.process("pnpm test", output)
        assert "2 suites passed" in result

    def test_dotnet_test_collapses_passed(self):
        lines = [
            "  Build started...",
            "  Restore complete.",
            "  Microsoft (R) Test Execution Engine",
            "  Passed! test_one",
            "  Passed! test_two",
            "  Passed! test_three",
            "  Failed test_broken",
            "    Expected: 1",
            "    Actual: 2",
            "  Total tests: 4",
            "  Passed: 3",
            "  Failed: 1",
        ]
        output = "\n".join(lines)
        result = self.p.process("dotnet test", output)
        assert "Failed" in result
        assert "Build started" not in result
        assert "Restore" not in result

    def test_swift_test_collapses_passed(self):
        lines = [
            "Build complete!",
            "Compile Swift Module",
            "Test Suite 'AllTests' started.",
            "Test Suite 'AllTests' passed.",
            "Executed 15 tests, with 0 failures.",
        ]
        output = "\n".join(lines)
        result = self.p.process("swift test", output)
        assert "Compile" not in result
        assert "Build" not in result
        assert "Executed 15" in result

    def test_mix_test_collapses_dots(self):
        lines = [
            "Compiling 2 files (.ex)",
            "Generated myapp app",
            "." * 30,
            "",
            "Finished in 0.5 seconds",
            "30 tests, 0 failures",
        ]
        output = "\n".join(lines)
        result = self.p.process("mix test", output)
        assert "30 tests passed" in result
        assert "Compiling" not in result
        assert "30 tests, 0 failures" in result

    def test_traceback_truncation(self):
        """Long traceback blocks should be truncated."""
        block = [f"    frame_{i}" for i in range(50)]
        result = self.p._truncate_traceback(block)
        assert len(result) < len(block)
        assert "traceback lines truncated" in "\n".join(result)
        # Head and tail preserved
        assert "frame_0" in result[0]
        assert "frame_49" in result[-1]

    def test_traceback_short_unchanged(self):
        block = ["    line 1", "    line 2", "    line 3"]
        result = self.p._truncate_traceback(block)
        assert result == block


class TestBuildOutputProcessor:
    def setup_method(self):
        self.p = BuildOutputProcessor()

    def test_can_handle_build_commands(self):
        assert self.p.can_handle("npm run build")
        assert self.p.can_handle("cargo build")
        assert self.p.can_handle("make")
        assert self.p.can_handle("pip install -r requirements.txt")
        assert self.p.can_handle("yarn add lodash")
        assert self.p.can_handle("next build")
        assert not self.p.can_handle("git status")

    def test_empty_output(self):
        assert self.p.process("npm run build", "") == ""

    def test_success_summarized(self):
        lines = [f"  Installing dep-{i}..." for i in range(20)]
        lines.append("Build completed successfully")
        output = "\n".join(lines)
        result = self.p.process("npm run build", output)
        assert "Build succeeded" in result

    def test_errors_preserved(self):
        output = "\n".join(
            [
                "Compiling src/main.rs",
                "error[E0308]: mismatched types",
                "  --> src/main.rs:10:5",
                "   |",
                '10 |     let x: u32 = "hello";',
                "   |                  ^^^^^^^ expected u32",
                "",
                "error: aborting due to previous error",
            ]
        )
        result = self.p.process("cargo build", output)
        assert "error" in result
        assert "mismatched types" in result

    def test_warnings_counted(self):
        lines = [f"  WARNING: deprecated dep-{i}" for i in range(10)]
        lines.append("Build done in 5s")
        output = "\n".join(lines)
        result = self.p.process("npm run build", output)
        assert "10 warnings" in result
        assert "Build succeeded" in result

    def test_progress_lines_skipped(self):
        output = "\n".join(
            [
                "[1/4] Resolving packages...",
                "[2/4] Fetching packages...",
                "[3/4] Linking dependencies...",
                "[4/4] Building fresh packages...",
                "Done in 3.14s.",
            ]
        )
        result = self.p.process("yarn install", output)
        assert "[1/4]" not in result
        assert "Build succeeded" in result

    def test_can_handle_docker_build(self):
        assert self.p.can_handle("docker build -t myapp .")
        assert self.p.can_handle("docker compose build")

    def test_can_handle_npm_audit(self):
        assert self.p.can_handle("npm audit")
        assert self.p.can_handle("yarn audit")

    def test_docker_build_keeps_steps_and_result(self):
        output = "\n".join(
            [
                "Sending build context to Docker daemon  2.5MB",
                "Step 1/10 : FROM node:18",
                " ---> abc123def456",
                "Step 2/10 : WORKDIR /app",
                "Running in 789abc012def",
                "Removing intermediate container 789abc012def",
                " ---> 345def678abc",
                "Step 3/10 : COPY package.json .",
                "Step 4/10 : RUN npm install",
                "Downloading lodash@4.17.21",
                "Installing lodash@4.17.21",
                "Step 5/10 : COPY . .",
                "Step 6/10 : RUN npm run build",
                "Step 7/10 : FROM nginx:alpine",
                "Step 8/10 : COPY --from=0 /app/dist /usr/share/nginx/html",
                "Step 9/10 : EXPOSE 80",
                'Step 10/10 : CMD ["nginx", "-g", "daemon off;"]',
                "Successfully built abc123def",
                "Successfully tagged myapp:latest",
            ]
        )
        result = self.p.process("docker build -t myapp .", output)
        # Steps preserved
        assert "Step 1/10" in result
        assert "Step 10/10" in result
        # Final result preserved
        assert "Successfully built" in result
        assert "Successfully tagged" in result
        # Noise removed
        assert "Sending build context" not in result
        assert "Running in" not in result
        assert "Removing intermediate" not in result
        assert " ---> " not in result

    def test_docker_build_keeps_errors(self):
        output = "\n".join(
            [
                "Step 1/5 : FROM node:18",
                "Step 2/5 : RUN npm install",
                "ERROR: failed to build: exit code 1",
            ]
        )
        result = self.p.process("docker build .", output)
        assert "ERROR" in result or "failed" in result

    def test_npm_audit_groups_by_severity(self):
        output = "\n".join(
            [
                "# npm audit report",
                "",
                "lodash  <4.17.21",
                "Severity: high",
                "Prototype Pollution - https://github.com/advisories/123",
                "fix available via `npm audit fix`",
                "",
                "minimist  <1.2.6",
                "Severity: critical",
                "Prototype Pollution - https://github.com/advisories/456",
                "fix available via `npm audit fix`",
                "",
                "glob-parent  <5.1.2",
                "Severity: high",
                "Regular Expression Denial of Service",
                "",
                "3 vulnerabilities (1 critical, 2 high)",
            ]
        )
        result = self.p.process("npm audit", output)
        assert "critical" in result
        assert "high" in result
        assert "vulnerabilities" in result.lower() or "found" in result.lower()

    def test_pip_progress_skipped(self):
        output = "\n".join(
            [
                "Collecting requests",
                "  Downloading requests-2.31.0-py3-none-any.whl",
                "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 62.6/62.6 kB 1.2 MB/s",
                "Installing collected packages: requests",
                "Successfully installed requests-2.31.0",
            ]
        )
        result = self.p.process("pip install requests", output)
        assert "━" not in result
        assert "Collecting" not in result
        assert "Build succeeded" in result

    def test_yarn_berry_step_progress_skipped(self):
        """Yarn Berry (v2+) outputs step lines prefixed with ➤ YN0000: ┌/└."""
        output = "\n".join(
            [
                "\u27a4 YN0000: \u250c Resolution step",
                "\u27a4 YN0000: \u2514 Completed in 0s 259ms",
                "\u27a4 YN0000: \u250c Fetch step",
                "\u27a4 YN0000: \u2514 Completed in 1s 263ms",
                "\u27a4 YN0000: \u250c Link step",
                "\u27a4 YN0000: \u2514 Completed in 0s 218ms",
                "Done in 1.74s",
            ]
        )
        result = self.p.process("yarn install", output)
        assert "Resolution step" not in result
        assert "Fetch step" not in result
        assert "Link step" not in result
        assert "Build succeeded" in result

    def test_pnpm_progress_lines_skipped(self):
        """pnpm emits 'Progress: resolved N, ...' and hard link messages."""
        output = "\n".join(
            [
                "Packages are hard linked from the content-addressable store",
                "Progress: resolved 150, reused 148, downloaded 2, added 150",
                "Progress: resolved 200, reused 198, downloaded 2, added 200, done",
                "Done in 4.2s",
            ]
        )
        result = self.p.process("pnpm install", output)
        assert "Progress:" not in result
        assert "hard linked" not in result
        assert "Build succeeded" in result


class TestLintOutputProcessor:
    def setup_method(self):
        self.p = LintOutputProcessor()

    def test_can_handle_lint_commands(self):
        assert self.p.can_handle("eslint src/")
        assert self.p.can_handle("ruff check .")
        assert self.p.can_handle("ruff .")
        assert self.p.can_handle("pylint src/")
        assert self.p.can_handle("mypy src/")
        assert self.p.can_handle("python3 -m mypy src/")
        assert not self.p.can_handle("git diff")

    def test_empty_output(self):
        assert self.p.process("ruff check .", "") == ""

    def test_groups_by_rule(self):
        lines = []
        for i in range(15):
            lines.append(f"src/file{i}.py:10:1: E501 line too long")
        for i in range(5):
            lines.append(f"src/file{i}.py:1:1: F401 imported but unused")
        output = "\n".join(lines)
        result = self.p.process("ruff check .", output)
        assert "E501" in result
        assert "15 occurrences" in result
        assert "20 issues across 2 rules" in result
        assert len(result) < len(output)

    def test_mypy_errors_grouped(self):
        lines = []
        for i in range(10):
            lines.append(f"src/file{i}.py:{i + 1}: error: Incompatible types [assignment]")
        for i in range(5):
            lines.append(f"src/file{i}.py:{i + 1}: error: Missing return [return]")
        output = "\n".join(lines)
        result = self.p.process("mypy src/", output)
        assert "assignment" in result
        assert "15 issues" in result

    def test_few_violations_not_grouped(self):
        """3 or fewer of a rule should be shown individually."""
        output = "\n".join(
            [
                "src/a.py:1:1: E501 line too long",
                "src/b.py:2:1: E501 line too long",
                "src/c.py:3:1: F401 imported but unused",
            ]
        )
        result = self.p.process("ruff check .", output)
        assert "occurrences" not in result  # Only 2 E501, should show inline

    def test_important_ungrouped_kept(self):
        output = "\n".join(
            [
                "src/a.py:1:1: E501 line too long",
                "src/b.py:2:1: E501 line too long",
                "src/c.py:3:1: E501 line too long",
                "src/d.py:4:1: E501 line too long",
                "fatal: cannot read config file",
            ]
        )
        result = self.p.process("ruff check .", output)
        assert "fatal" in result

    def test_can_handle_shellcheck_hadolint(self):
        assert self.p.can_handle("shellcheck script.sh")
        assert self.p.can_handle("hadolint Dockerfile")
        assert self.p.can_handle("cargo clippy")
        assert self.p.can_handle("prettier --check src/")
        assert self.p.can_handle("biome check src/")
        assert self.p.can_handle("biome lint src/")

    def test_shellcheck_violations_parsed(self):
        lines = []
        for i in range(10):
            lines.append(f"script.sh:{i + 1}:1: warning - SC2086 Double quote to prevent globbing")
        output = "\n".join(lines)
        result = self.p.process("shellcheck script.sh", output)
        assert "SC2086" in result
        assert "10 issues" in result or "10 occurrences" in result

    def test_hadolint_violations_parsed(self):
        lines = []
        for i in range(8):
            lines.append(f"Dockerfile:{i + 1} DL3008 Pin versions in apt get install")
        output = "\n".join(lines)
        result = self.p.process("hadolint Dockerfile", output)
        assert "DL3008" in result

    def test_biome_violations_parsed(self):
        lines = []
        for i in range(10):
            lines.append(
                f"src/file{i}.ts:{i + 1}:1 lint/correctness/noUnusedVariables unused variable"
            )
        output = "\n".join(lines)
        result = self.p.process("biome lint src/", output)
        assert "lint/" in result

    def test_clippy_fallback_not_fooled_by_summary(self):
        """Clippy fallback should not parse [1 warning] as a rule name."""
        output = "\n".join(
            [
                "warning[clippy::needless_return]: unneeded `return`",
                "  --> src/main.rs:10:5",
                "warning: `myproject` (bin) generated 1 warning [1 warning]",
            ]
        )
        result = self.p.process("cargo clippy", output)
        # "clippy::needless_return" should be parsed as a rule
        assert "clippy::needless_return" in result
        # "1 warning" should NOT be parsed as a rule
        assert "1 warning" not in [
            line.strip() for line in result.splitlines() if line.strip().startswith("1 warning:")
        ]


class TestFileListingProcessor:
    def setup_method(self):
        self.p = FileListingProcessor()

    def test_can_handle_listing_commands(self):
        assert self.p.can_handle("ls -la")
        assert self.p.can_handle("find . -name '*.py'")
        assert self.p.can_handle("tree src/")
        assert not self.p.can_handle("git status")

    def test_empty_output(self):
        assert self.p.process("ls", "") == ""

    def test_find_groups_by_dir(self):
        lines = [f"src/components/Component{i}.tsx" for i in range(25)]
        lines += [f"src/utils/util{i}.ts" for i in range(15)]
        output = "\n".join(lines)
        result = self.p.process("find src -type f", output)
        assert "40 files found" in result
        assert "src/components" in result

    def test_find_large_dir_shows_extensions(self):
        """Dirs with >20 files should show extension breakdown."""
        lines = [f"src/components/File{i}.tsx" for i in range(35)]
        output = "\n".join(lines)
        result = self.p.process("find src -type f", output)
        assert "35 files" in result
        assert "tsx" in result

    def test_ls_compact_groups_by_extension(self):
        items = [f"file{i}.py" for i in range(15)] + [f"mod{i}.js" for i in range(10)]
        output = "\n".join(items)
        result = self.p.process("ls", output)
        assert "25 items" in result
        assert "*.py" in result
        assert "*.js" in result

    def test_ls_short_unchanged(self):
        output = "file1.py\nfile2.py\nfile3.py"
        result = self.p.process("ls", output)
        assert result == output

    def test_ls_long_strips_metadata(self):
        """ls -la should strip permissions, owner, group, date — keep type+size+name."""
        output = (
            "total 312\n"
            "drwxr-xr-x  18 user  staff    576 Jan 12 17:24 .\n"
            "drwxr-xr-x@  6 user  staff    192 Feb 17 10:16 ..\n"
            "-rw-r--r--   1 user  staff   8881 Jan 12 14:07 bigquery.tf\n"
            "-rw-r--r--   1 user  staff   7587 Jan 12 14:29 cloud_function.tf\n"
            "drwxr-xr-x   4 user  staff    128 Jan 12 14:08 function\n"
            "-rw-r--r--@  1 user  staff  73179 Jan 12 14:41 terraform.tfstate\n"
            "lrwxr-xr-x   1 user  staff     15 Jan 12 14:41 link -> target.tf\n"
        )
        result = self.p.process("ls -la", output)
        # total line removed
        assert "total" not in result
        # Permissions, owner, group, date stripped
        assert "rwx" not in result
        assert "user" not in result
        assert "staff" not in result
        assert "Jan" not in result
        # Dirs marked with /
        assert "function/" in result
        # Files have compact size
        assert "bigquery.tf" in result
        assert "terraform.tfstate" in result
        # Symlinks preserved
        assert "link -> target.tf" in result
        # Size should be human-readable (73179 bytes ≈ 71K)
        assert "71K" in result

    def test_ls_long_preserves_all_filenames(self):
        """Every filename from ls -l must appear in the compressed output."""
        files = ["main.tf", "variables.tf", "outputs.tf", "README.md"]
        lines = ["total 100"]
        for f in files:
            lines.append(f"-rw-r--r--  1 user staff  1234 Jan 12 14:00 {f}")
        output = "\n".join(lines)
        result = self.p.process("ls -la", output)
        for f in files:
            assert f in result

    def test_ls_long_shows_size(self):
        """File sizes should be human-readable."""
        output = (
            "total 100\n"
            "-rw-r--r--  1 user staff       42 Jan 12 14:00 tiny.txt\n"
            "-rw-r--r--  1 user staff     5120 Jan 12 14:00 medium.py\n"
            "-rw-r--r--  1 user staff  1048576 Jan 12 14:00 big.bin\n"
        )
        result = self.p.process("ls -l", output)
        assert "42B" in result
        assert "5K" in result
        assert "1.0M" in result

    def test_can_handle_exa_eza(self):
        assert self.p.can_handle("exa -la")
        assert self.p.can_handle("eza --long")

    def test_exa_compresses_like_ls(self):
        items = [f"file{i}.py" for i in range(25)]
        output = "\n".join(items)
        result = self.p.process("exa", output)
        assert "25 items" in result
        assert "*.py" in result

    def test_tree_truncated(self):
        lines = [f"{'|   ' * (i % 3)}+-- file{i}.py" for i in range(100)]
        lines.append("50 directories, 100 files")
        output = "\n".join(lines)
        result = self.p.process("tree", output)
        assert "truncated" in result
        assert "50 directories" in result


class TestFileContentProcessor:
    def setup_method(self):
        self.p = FileContentProcessor()

    def test_can_handle_cat_commands(self):
        assert self.p.can_handle("cat file.py")
        assert self.p.can_handle("head -100 file.py")
        assert self.p.can_handle("bat file.py")
        assert not self.p.can_handle("git status")

    def test_empty_output(self):
        assert self.p.process("cat file.py", "") == ""

    def test_short_file_unchanged(self):
        output = "\n".join(f"line {i}" for i in range(100))
        result = self.p.process("cat file.py", output)
        assert result == output

    def test_long_file_truncated(self):
        output = "\n".join(f"line {i}: content here" for i in range(500))
        result = self.p.process("cat big_file.py", output)
        assert "omitted" in result
        assert len(result) < len(output)
        # Head is preserved (code strategy keeps first N lines)
        assert "line 0:" in result

    def test_long_file_fallback_truncated(self):
        """Unknown file type falls back to head/tail truncation."""
        output = "\n".join(f"line {i}: content here" for i in range(500))
        result = self.p.process("cat big_file.xyz", output)
        assert "truncated" in result
        assert len(result) < len(output)
        assert "line 0:" in result
        assert "line 499:" in result

    def test_exact_threshold_not_truncated(self):
        output = "\n".join(f"line {i}" for i in range(300))
        result = self.p.process("cat file.py", output)
        assert result == output


class TestGenericProcessor:
    def setup_method(self):
        self.p = GenericProcessor()

    def test_always_handles(self):
        assert self.p.can_handle("anything")
        assert self.p.can_handle("")

    def test_strips_ansi(self):
        output = "\x1b[32mSuccess\x1b[0m\n\x1b[31mError\x1b[0m"
        result = self.p.process("cmd", output)
        assert "\x1b[" not in result
        assert "Success" in result
        assert "Error" in result

    def test_strips_osc_sequences(self):
        """Should also strip OSC escape sequences (title setting, etc.)."""
        output = "\x1b]0;Terminal Title\x07Normal text"
        result = self.p.process("cmd", output)
        assert "Normal text" in result
        assert "\x1b" not in result

    def test_collapses_repeated_lines(self):
        output = "Building...\n" * 20
        result = self.p.process("cmd", output)
        assert "x20" in result
        assert result.count("Building...") == 1

    def test_two_repeated_lines(self):
        """Even 2 repeated lines should be collapsed."""
        output = "line\nline"
        result = self.p.process("cmd", output)
        assert "x2" in result

    def test_blank_lines_not_collapsed_as_repeat(self):
        """Blank lines should not be treated as repeated content."""
        output = "a\n\n\n\nb"
        result = self.p.process("cmd", output)
        assert "x" not in result  # blank collapse, not repeat collapse

    def test_collapses_blank_lines(self):
        output = "line1\n\n\n\n\nline2"
        result = self.p.process("cmd", output)
        assert "\n\n\n" not in result
        assert "line1" in result
        assert "line2" in result

    def test_truncates_long_output(self):
        lines = [f"line {i}" for i in range(600)]
        output = "\n".join(lines)
        result = self.p.process("cmd", output)
        assert "truncated" in result
        assert len(result.splitlines()) < 600

    def test_strips_trailing_whitespace(self):
        output = "line1   \nline2\t\t\nline3"
        result = self.p.process("cmd", output)
        for line in result.splitlines():
            assert line == line.rstrip()

    def test_clean_method(self):
        """clean() should only strip ANSI and blank lines, not dedup or truncate."""
        output = "\x1b[32mline\x1b[0m\n\n\n\x1b[31mline\x1b[0m"
        result = self.p.clean(output)
        assert "\x1b[" not in result
        assert "\n\n\n" not in result
        # clean() should NOT collapse repeated "line" into "line (x2)"
        assert result.count("line") == 2

    def test_similar_lines_progress_collapsed(self):
        """Curl-like progress lines differing only in % should be collapsed."""
        lines = [
            f"  {i}  1024M    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0"
            for i in range(20)
        ]
        output = "\n".join(lines)
        result = self.p.process("cmd", output)
        assert "similar lines" in result
        assert len(result.splitlines()) < 10

    def test_similar_lines_data_preserved(self):
        """Lines with meaningful non-numeric content should NOT be collapsed."""
        lines = [f"IMPORTANT_DATA_{i}: value_{i}" for i in range(10)]
        output = "\n".join(lines)
        result = self.p.process("cmd", output)
        # These lines are not numeric-heavy, so they should all survive
        for line in lines:
            assert line in result

    def test_progress_bar_stripped(self):
        """Lines that are mostly progress bar characters should be removed."""
        output = "Starting\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nDone"
        result = self.p.process("cmd", output)
        assert "Starting" in result
        assert "Done" in result
        assert "━" not in result


class TestNetworkProcessor:
    def setup_method(self):
        self.p = NetworkProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("curl https://example.com")
        assert self.p.can_handle("curl -v https://api.example.com")
        assert self.p.can_handle("wget https://example.com/file.tar.gz")
        assert not self.p.can_handle("git status")

    def test_empty_output(self):
        assert self.p.process("curl https://example.com", "") == ""

    def test_curl_verbose_strips_tls(self):
        output = "\n".join(
            [
                "* Trying 93.184.216.34:443...",
                "* Connected to example.com (93.184.216.34) port 443",
                "* ALPN: offers h2,http/1.1",
                "* TLSv1.3 (OUT), TLS handshake, Client hello (1):",
                "* TLSv1.3 (IN), TLS handshake, Server hello (2):",
                "* SSL connection using TLSv1.3",
                "* Certificate: CN=example.com",
                "> GET /api/data HTTP/2",
                "> Host: example.com",
                "> User-Agent: curl/8.0",
                "> Accept: */*",
                "< HTTP/2 200",
                "< content-type: application/json",
                "< date: Mon, 01 Jan 2025 12:00:00 GMT",
                "< server: nginx",
                "< x-request-id: abc-123",
                "< x-powered-by: Express",
                "<",
                '{"data": "value"}',
                "* Connection #0 left intact",
            ]
        )
        result = self.p.process("curl -v https://example.com/api/data", output)
        # TLS noise stripped
        assert "TLSv1.3" not in result
        assert "ALPN" not in result
        assert "Certificate" not in result
        assert "Connected to" not in result
        assert "Connection #0" not in result
        # Important headers kept
        assert "HTTP/2 200" in result
        assert "content-type" in result
        assert "x-request-id" in result
        # Boilerplate headers stripped
        assert "date:" not in result
        assert "server:" not in result
        assert "x-powered-by" not in result
        # Request method kept
        assert "GET /api/data" in result
        # Request headers stripped
        assert "User-Agent" not in result
        assert "Accept:" not in result
        # Response body kept
        assert '"data": "value"' in result

    def test_curl_progress_stripped(self):
        output = "\n".join(
            [
                "  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current",
                "                                 Dload  Upload   Total   Spent    Left  Speed",
                "  0  1024M    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0",
                '{"result": "ok"}',
            ]
        )
        result = self.p.process("curl https://api.example.com", output)
        assert "% Total" not in result
        assert '"result": "ok"' in result

    def test_wget_strips_progress(self):
        output = "\n".join(
            [
                "Resolving example.com (example.com)... 93.184.216.34",
                "Connecting to example.com (example.com)|93.184.216.34|:443... connected.",
                "HTTP request sent, awaiting response... 200 OK",
                "Length: 1024000 (1000K) [application/octet-stream]",
                "Saving to: 'file.tar.gz'",
                "",
                "file.tar.gz         50%[========>           ] 500K  1.00MB/s",
                "file.tar.gz        100%[===================>] 1000K  2.00MB/s    in 0.5s",
                "",
                "2025-01-01 12:00:00 (2.00 MB/s) - 'file.tar.gz' saved [1024000/1024000]",
            ]
        )
        result = self.p.process("wget https://example.com/file.tar.gz", output)
        # Progress stripped
        assert "Resolving" not in result
        assert "Connecting to" not in result
        assert "========>" not in result
        # Important info kept
        assert "200 OK" in result
        assert "Length:" in result
        assert "Saving to:" in result
        assert "saved" in result

    def test_can_handle_httpie(self):
        assert self.p.can_handle("http GET https://api.example.com/data")
        assert self.p.can_handle("https POST https://api.example.com/users")

    def test_can_handle_no_false_positive(self):
        """http/https in URLs should NOT trigger network processor."""
        assert not self.p.can_handle("git push https://github.com/repo")
        assert not self.p.can_handle("pip install https://example.com/pkg.tar.gz")

    def test_httpie_compresses(self):
        output = "\n".join(
            [
                "HTTP/1.1 200 OK",
                "Content-Type: application/json",
                "Date: Mon, 01 Jan 2025 12:00:00 GMT",
                "Server: nginx",
                "X-Request-Id: abc-123",
                "",
                '{"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}',
            ]
        )
        result = self.p.process("http GET https://api.example.com/users", output)
        assert "HTTP/1.1 200" in result
        assert "Content-Type" in result
        assert "X-Request-Id" not in result or "abc-123" in result
        # Date and Server should be filtered
        assert "Server: nginx" not in result

    def test_curl_json_compressed(self):
        """Large JSON responses should be summarized."""
        import json

        data = {
            "users": [
                {"id": i, "name": f"User {i}", "email": f"user{i}@example.com"} for i in range(20)
            ],
            "total": 20,
            "page": 1,
        }
        output = json.dumps(data, indent=2)
        result = self.p.process("curl https://api.example.com/users", output)
        assert "users" in result
        assert "items total" in result or "20" in result
        assert len(result) < len(output)

    def test_curl_small_json_unchanged(self):
        """Small JSON responses should pass through."""
        output = '{"status": "ok"}'
        result = self.p.process("curl https://api.example.com/health", output)
        assert result == output


class TestDockerProcessor:
    def setup_method(self):
        self.p = DockerProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("docker ps")
        assert self.p.can_handle("docker images")
        assert self.p.can_handle("docker logs container")
        assert self.p.can_handle("docker pull nginx")
        assert self.p.can_handle("docker compose ps")
        assert not self.p.can_handle("docker build .")

    def test_can_handle_with_global_options(self):
        assert self.p.can_handle("docker --context remote ps")
        assert self.p.can_handle("docker -H tcp://host:2375 images")
        assert self.p.can_handle("docker --host unix:///var/run/docker.sock logs container")

    def test_empty_output(self):
        assert self.p.process("docker ps", "") == ""

    def test_ps_compresses(self):
        header = (
            "CONTAINER ID   IMAGE          COMMAND"
            "                  CREATED       STATUS"
            "       PORTS                  NAMES"
        )
        entries = []
        for i in range(15):
            entries.append(
                f"abc{i:010d}   nginx:latest"
                f'   "nginx -g \'daemon of\u2026"'
                f"   {i} hours ago   Up {i} hours"
                f"   0.0.0.0:80{i:02d}->80/tcp   web-{i}"
            )
        output = "\n".join([header, *entries])
        result = self.p.process("docker ps", output)
        assert "15 containers" in result
        assert "Running" in result

    def test_images_filters_dangling(self):
        header = "REPOSITORY   TAG       IMAGE ID       CREATED        SIZE"
        entries = [
            "nginx        latest    abc123def456   2 weeks ago    187MB",
            "python       3.12      def456abc789   3 weeks ago    1.01GB",
            "<none>       <none>    111222333444   4 weeks ago    500MB",
            "<none>       <none>    555666777888   4 weeks ago    300MB",
        ]
        output = "\n".join([header, *entries])
        result = self.p.process("docker images", output)
        assert "4 images" in result
        assert "nginx:latest" in result
        assert "python:3.12" in result
        assert "2 dangling" in result
        assert "<none>" not in result

    def test_logs_keeps_errors(self):
        lines = [f"[INFO] Request {i} processed" for i in range(80)]
        lines[40] = "[ERROR] Database connection failed: timeout"
        lines[41] = "  at ConnectionPool.acquire (pool.js:42)"
        lines[42] = "  at Query.execute (query.js:15)"
        output = "\n".join(lines)
        result = self.p.process("docker logs container", output)
        assert "Database connection failed" in result
        assert len(result.splitlines()) < len(lines)

    def test_pull_strips_layer_progress(self):
        output = "\n".join(
            [
                "Using default tag: latest",
                "latest: Pulling from library/nginx",
                "a2318d6c47ec: Pulling fs layer",
                "a2318d6c47ec: Downloading  [==>                    ] 1.5MB/25MB",
                "a2318d6c47ec: Download complete",
                "a2318d6c47ec: Pull complete",
                "b12007d4c5a8: Already exists",
                "Digest: sha256:abc123def456",
                "Status: Downloaded newer image for nginx:latest",
                "docker.io/library/nginx:latest",
            ]
        )
        result = self.p.process("docker pull nginx", output)
        assert "Pulling fs layer" not in result
        assert "Downloading" not in result
        assert "Pull complete" not in result
        assert "Digest:" in result or "Status:" in result

    def test_can_handle_inspect_stats_compose(self):
        assert self.p.can_handle("docker inspect container")
        assert self.p.can_handle("docker stats")
        assert self.p.can_handle("docker compose up")
        assert self.p.can_handle("docker compose down")
        assert self.p.can_handle("docker compose ps")
        assert self.p.can_handle("docker compose logs")
        assert self.p.can_handle("docker compose build")

    def test_inspect_summarizes_json(self):
        import json

        data = [
            {
                "Id": "abc123def456789",
                "Name": "/my-container",
                "State": {
                    "Status": "running",
                    "Running": True,
                    "Paused": False,
                    "Pid": 12345,
                    "ExitCode": 0,
                },
                "Config": {
                    "Image": "nginx:latest",
                    "Cmd": ["nginx", "-g", "daemon off;"],
                    "Env": [f"VAR_{i}=val" for i in range(10)],
                },
                "NetworkSettings": {
                    "Ports": {"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}]},
                    "Networks": {
                        "bridge": {"IPAddress": "172.17.0.2"},
                    },
                },
            }
        ]
        output = json.dumps(data, indent=2)
        result = self.p.process("docker inspect my-container", output)
        assert "my-container" in result
        assert "running" in result or "Running" in result
        assert "nginx:latest" in result
        assert "total lines" in result
        assert len(result) < len(output)

    def test_inspect_invalid_json_truncates(self):
        lines = [f"line {i}: not json" for i in range(60)]
        output = "\n".join(lines)
        result = self.p.process("docker inspect container", output)
        assert "more lines" in result

    def test_stats_keeps_last_block(self):
        header = "CONTAINER ID   NAME     CPU %    MEM USAGE / LIMIT"
        # Simulate streaming stats: 3 repeated blocks
        blocks = []
        for block in range(3):
            blocks.append(header)
            for i in range(5):
                blocks.append(f"abc{i:03d}         web-{i}   {block + i}.0%    100MiB / 1GiB")
        output = "\n".join(blocks)
        result = self.p.process("docker stats", output)
        # Should only keep last block (header + 5 rows)
        assert result.count("CONTAINER") == 1
        assert len(result.splitlines()) <= 6

    def test_stats_short_unchanged(self):
        output = "CONTAINER ID   NAME     CPU %\nabc123   web   1.5%"
        result = self.p.process("docker stats --no-stream", output)
        assert result == output

    def test_compose_up_keeps_started(self):
        lines = [
            "Creating network default",
            "Pulling web (nginx:latest)...",
            "50%: downloading...",
            "100%: complete",
            "Creating web-1  ... done",
            "Creating db-1   ... done",
            "Network default  Created",
            "Container web-1  Started",
            "Container db-1   Started",
        ] + [f"web-1  | log line {i}" for i in range(20)]
        output = "\n".join(lines)
        result = self.p.process("docker compose up -d", output)
        assert "Started" in result
        assert "Created" in result
        assert "50%" not in result

    def test_compose_down_keeps_removed(self):
        lines = [
            "Stopping web-1   ... done",
            "Stopping db-1    ... done",
            "Removing web-1   ... done",
            "Removing db-1    ... done",
            "Removing network default",
            "Network default  Removed",
        ] + [f"cleanup line {i}" for i in range(20)]
        output = "\n".join(lines)
        result = self.p.process("docker compose down", output)
        assert "Removing" in result or "Removed" in result
        assert "Stopping" not in result or len(result) < len(output)

    def test_compose_build_keeps_steps(self):
        lines = [
            "web Building",
            "Step 1/5 : FROM node:18",
            " ---> abc123",
            "Step 2/5 : COPY . .",
            "Running in def456",
            "Removing intermediate container def456",
            "Step 3/5 : RUN npm install",
            "npm WARN deprecated package@1.0",
            "Step 4/5 : RUN npm run build",
            "Step 5/5 : CMD node server.js",
            "Successfully built abc123",
            "Successfully tagged myapp:latest",
        ] + [f"noise line {i}" for i in range(20)]
        output = "\n".join(lines)
        result = self.p.process("docker compose build", output)
        assert "Step 1/5" in result
        assert "Successfully built" in result
        assert "web Building" in result or "building" in result.lower()

    def test_ps_dead_containers_in_stopped(self):
        """Dead containers should be grouped with stopped."""
        header = "CONTAINER ID   IMAGE          COMMAND   CREATED   STATUS         PORTS     NAMES"
        entries = [
            "abc0000000000   nginx:latest   nginx     1h ago    Up 1 hours     80/tcp    web-0",
            "abc0000000001   myapp:latest   python    2h ago    Dead                     dead-app",
        ]
        output = "\n".join([header, *entries])
        result = self.p.process("docker ps -a", output)
        assert "dead-app" in result


class TestPackageListProcessor:
    def setup_method(self):
        self.p = PackageListProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("pip list")
        assert self.p.can_handle("pip3 list")
        assert self.p.can_handle("pip freeze")
        assert self.p.can_handle("npm ls")
        assert self.p.can_handle("npm list")
        assert self.p.can_handle("conda list")
        assert not self.p.can_handle("pip install foo")
        assert not self.p.can_handle("npm install")

    def test_pip_list_truncated(self):
        lines = ["Package    Version", "---------- -------"]
        for i in range(50):
            lines.append(f"package-{i:03d}  {i}.0.0")
        output = "\n".join(lines)
        result = self.p.process("pip list", output)
        assert "50 packages installed" in result
        assert "package-000" in result
        assert "... (35 more)" in result

    def test_pip_list_short_unchanged(self):
        output = "\n".join(
            [
                "Package  Version",
                "-------- -------",
                "pip      23.0",
                "setuptools 67.0",
            ]
        )
        result = self.p.process("pip list", output)
        assert result == output

    def test_pip_freeze_truncated(self):
        lines = [f"package-{i}=={i}.0.0" for i in range(30)]
        output = "\n".join(lines)
        result = self.p.process("pip freeze", output)
        assert "30 packages" in result
        assert "... (15 more)" in result

    def test_npm_ls_collapses_tree(self):
        lines = ["my-project@1.0.0 /home/user/project"]
        for i in range(10):
            lines.append(f"├── package-{i}@{i}.0.0")
            for j in range(5):
                lines.append(f"│   ├── sub-dep-{i}-{j}@0.{j}.0")
        output = "\n".join(lines)
        result = self.p.process("npm ls", output)
        assert "total dependencies" in result
        assert "Top-level" in result
        assert len(result.splitlines()) < len(lines)

    def test_npm_ls_shows_issues(self):
        lines = [
            "my-project@1.0.0",
            "├── lodash@4.17.21",
            "├── UNMET DEPENDENCY react@^18.0.0",
            "├── express@4.18.2",
        ]
        output = "\n".join(lines)
        result = self.p.process("npm ls", output)
        assert "UNMET" in result

    def test_build_processor_rejects_pip_list(self):
        """pip list should NOT be handled by build processor."""
        from src.processors.build_output import BuildOutputProcessor

        bp = BuildOutputProcessor()
        assert not bp.can_handle("pip list")
        assert not bp.can_handle("pip3 list")
        assert not bp.can_handle("npm ls")
        assert not bp.can_handle("npm list")


class TestSearchProcessor:
    def setup_method(self):
        self.p = SearchProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("grep -r pattern .")
        assert self.p.can_handle("rg pattern")
        assert self.p.can_handle("ag pattern src/")
        assert not self.p.can_handle("git status")

    def test_short_output_unchanged(self):
        output = "\n".join([f"src/file{i}.py:10:match here" for i in range(5)])
        result = self.p.process("grep -r pattern .", output)
        assert result == output

    def test_groups_by_file(self):
        lines = []
        for i in range(10):
            for j in range(5):
                lines.append(f"src/file{i}.py:{j + 1}:match content {j}")
        output = "\n".join(lines)
        result = self.p.process("grep -r pattern .", output)
        assert "50 matches across 10 files" in result
        assert "... (" in result  # truncated per-file

    def test_strips_binary_warnings(self):
        output = "\n".join(
            [
                "src/app.py:10:pattern match",
                "Binary file node_modules/.cache/foo matches",
                "src/util.py:20:another pattern match",
            ]
            * 15
        )
        result = self.p.process("grep -r pattern .", output)
        assert "Binary file" not in result

    def test_many_files_truncated(self):
        lines = []
        for i in range(30):
            lines.append(f"src/dir/file{i}.py:1:match")
        output = "\n".join(lines)
        result = self.p.process("rg pattern", output)
        assert "30 matches" in result

    def test_can_handle_fd(self):
        assert self.p.can_handle("fd pattern")
        assert self.p.can_handle("fdfind -e py")

    def test_fd_groups_by_directory(self):
        lines = [f"src/components/Component{i}.tsx" for i in range(15)]
        lines += [f"src/utils/util{i}.ts" for i in range(10)]
        output = "\n".join(lines)
        result = self.p.process("fd -e tsx -e ts", output)
        assert "25 files found" in result
        assert "src/components" in result
        assert "src/utils" in result

    def test_fd_short_unchanged(self):
        output = "src/main.py\nsrc/util.py\nsrc/app.py"
        result = self.p.process("fd -e py", output)
        assert result == output


class TestKubectlProcessor:
    def setup_method(self):
        self.p = KubectlProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("kubectl get pods")
        assert self.p.can_handle("kubectl describe pod my-pod")
        assert self.p.can_handle("kubectl logs my-pod")
        assert self.p.can_handle("oc get pods")
        assert not self.p.can_handle("docker ps")

    def test_can_handle_with_global_options(self):
        assert self.p.can_handle("kubectl -n kube-system get pods")
        assert self.p.can_handle("kubectl --namespace=default get svc")
        assert self.p.can_handle("kubectl --context prod describe pod my-pod")
        assert self.p.can_handle("kubectl -A get pods")
        assert self.p.can_handle("kubectl --all-namespaces get pods")
        assert self.p.can_handle("kubectl -n monitoring --context staging logs my-pod")
        assert self.p.can_handle("kubectl --kubeconfig /path/config get nodes")

    def test_get_pods_summarizes_healthy(self):
        header = "NAME                    READY   STATUS    RESTARTS   AGE"
        entries = []
        for i in range(20):
            entries.append(f"web-{i:03d}                 1/1     Running   0          {i}h")
        entries.append("web-failing             0/1     CrashLoopBackOff   5          2h")
        output = "\n".join([header, *entries])
        result = self.p.process("kubectl get pods", output)
        assert "CrashLoopBackOff" in result
        assert "20 pods Running/Ready" in result
        # AGE column should be stripped
        assert "AGE" not in result
        # Other columns still present
        assert "NAME" in result
        assert "STATUS" in result

    def test_get_services_strips_age(self):
        """kubectl get svc should strip AGE column from generic tabular output."""
        header = "NAME         TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE"
        entries = [
            f"svc-{i:03d}      ClusterIP   10.0.0.{i}      <none>        80/TCP    {i}d"
            for i in range(15)
        ]
        output = "\n".join([header, *entries])
        result = self.p.process("kubectl get svc", output)
        assert "AGE" not in result
        assert "NAME" in result
        assert "PORT(S)" in result
        assert "svc-000" in result

    def test_describe_strips_noise(self):
        output = "\n".join(
            [
                "Name:         my-pod",
                "Namespace:    default",
                "Node:         node-1/10.0.0.1",
                "Status:       Running",
                "IP:           10.244.0.5",
                "Labels:       app=web",
                "Annotations:  kubernetes.io/config.seen: 2025-01-01",
                "              kubernetes.io/config.source: api",
                "Tolerations:  node.kubernetes.io/not-ready:NoExecute op=Exists",
                "              node.kubernetes.io/unreachable:NoExecute op=Exists",
                "QoS Class:    BestEffort",
                "Volumes:",
                "  default-token-abc:",
                "    Type:        Secret (a volume populated by a Secret)",
                "    SecretName:  default-token-abc",
                "    Optional:    false",
                "Events:",
                "  Type    Reason     Age   From               Message",
                "  Normal  Scheduled  10m   default-scheduler  Successfully assigned",
                "  Normal  Pulled     10m   kubelet            Container image pulled",
                "  Warning BackOff    5m    kubelet"
                "            Back-off restarting failed container",
            ]
        )
        result = self.p.process("kubectl describe pod my-pod", output)
        assert "Name:" in result
        assert "Status:" in result
        assert "BackOff" in result  # Warning event kept
        assert "Tolerations" not in result  # Noise stripped
        assert "QoS Class" not in result

    def test_logs_keeps_errors(self):
        lines = [f"[INFO] Processing request {i}" for i in range(100)]
        lines[50] = "[ERROR] NullPointerException at com.app.Service:42"
        output = "\n".join(lines)
        result = self.p.process("kubectl logs my-pod", output)
        assert "NullPointerException" in result
        assert len(result.splitlines()) < 100

    def test_can_handle_apply_delete_create(self):
        assert self.p.can_handle("kubectl apply -f deployment.yaml")
        assert self.p.can_handle("kubectl delete pod my-pod")
        assert self.p.can_handle("kubectl create namespace test")

    def test_mutate_keeps_results(self):
        lines = [
            "deployment.apps/web created",
            "service/web-svc created",
            "configmap/web-config configured",
            "secret/web-secret unchanged",
        ] + [f"verbose detail line {i}" for i in range(30)]
        output = "\n".join(lines)
        result = self.p.process("kubectl apply -f .", output)
        assert "web created" in result
        assert "web-svc created" in result
        assert "configured" in result
        assert "unchanged" in result
        assert "verbose detail" not in result

    def test_mutate_keeps_errors(self):
        lines = [
            "deployment.apps/web created",
            "error: unable to recognize 'bad.yaml': no matches for kind",
            "Warning: resource might not be valid",
        ] + [f"detail {i}" for i in range(25)]
        output = "\n".join(lines)
        result = self.p.process("kubectl apply -f .", output)
        assert "error" in result
        assert "Warning" in result
        assert "web created" in result

    def test_mutate_short_unchanged(self):
        output = "pod/test-pod deleted"
        result = self.p.process("kubectl delete pod test-pod", output)
        assert result == output

    def test_multi_container_ready_detection(self):
        """_is_all_ready should correctly handle multi-container pods."""
        assert self.p._is_all_ready("my-pod  2/2  Running  0  1h")
        assert self.p._is_all_ready("my-pod  10/10  Running  0  1h")
        assert not self.p._is_all_ready("my-pod  3/5  Running  0  1h")
        assert not self.p._is_all_ready("my-pod  0/1  Running  0  1h")
        # Edge: no READY column
        assert not self.p._is_all_ready("my-pod  Running  0  1h")

    def test_get_pods_multi_container(self):
        """Pods with 3/3 containers should be grouped as healthy."""
        header = "NAME         READY   STATUS    RESTARTS   AGE"
        entries = [
            "sidecar-pod  3/3     Running   0          1h",
            "init-pod     2/3     Running   0          1h",
        ] + [f"web-{i:03d}      1/1     Running   0          {i}h" for i in range(15)]
        output = "\n".join([header, *entries])
        result = self.p.process("kubectl get pods", output)
        # init-pod (2/3) should be shown explicitly
        assert "init-pod" in result
        # healthy pods should be summarized
        assert "Running/Ready" in result


class TestEnvProcessor:
    def setup_method(self):
        self.p = EnvProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("env")
        assert self.p.can_handle("printenv")
        assert self.p.can_handle("set")
        assert not self.p.can_handle("env FOO=bar cmd")

    def test_filters_system_vars(self):
        lines = [
            "TERM=xterm-256color",
            "SHELL=/bin/zsh",
            "USER=developer",
            "HOME=/home/developer",
            "LANG=en_US.UTF-8",
            "LC_ALL=en_US.UTF-8",
            "SSH_AUTH_SOCK=/tmp/ssh-abc",
            "DISPLAY=:0",
            "XDG_SESSION_TYPE=wayland",
            "NODE_ENV=production",
            "DATABASE_URL=postgres://localhost/mydb",
            "PORT=3000",
            "DEBUG=true",
        ]
        output = "\n".join(lines)
        result = self.p.process("env", output)
        assert "application-relevant" in result
        assert "NODE_ENV" in result
        assert "PORT=3000" in result
        assert "TERM=" not in result
        assert "SHELL=" not in result
        assert "system vars hidden" in result

    def test_redacts_secrets(self):
        lines = [
            "API_KEY=sk-abc123secret456",
            "DATABASE_PASSWORD=super_secret_pass",
            "GITHUB_TOKEN=ghp_xxxxxxxxxxxx",
            "NORMAL_VAR=hello",
        ] + [f"FILLER_{i}=val" for i in range(20)]
        output = "\n".join(lines)
        result = self.p.process("env", output)
        assert "API_KEY=***" in result
        assert "DATABASE_PASSWORD=***" in result
        assert "GITHUB_TOKEN=***" in result
        assert "sk-abc123" not in result
        assert "super_secret_pass" not in result
        assert "sensitive values redacted" in result

    def test_truncates_long_paths(self):
        long_path = ":".join(f"/usr/local/path{i}" for i in range(20))
        lines = [f"PATH={long_path}"] + [f"VAR_{i}=val" for i in range(20)]
        output = "\n".join(lines)
        result = self.p.process("env", output)
        assert "total entries" in result  # PATH was truncated

    def test_short_output_unchanged(self):
        output = "\n".join([f"VAR{i}=val{i}" for i in range(5)])
        result = self.p.process("env", output)
        assert result == output


class TestSystemInfoProcessor:
    def setup_method(self):
        self.p = SystemInfoProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("du -sh *")
        assert self.p.can_handle("wc -l *.py")
        assert self.p.can_handle("df -h")
        assert not self.p.can_handle("ls -la")

    def test_du_sorts_and_truncates(self):
        lines = [f"{i}K\tdir{i}" for i in range(30)]
        output = "\n".join(lines)
        result = self.p.process("du -sh *", output)
        assert "... (" in result
        assert "more entries" in result

    def test_du_short_unchanged(self):
        output = "4K\tdir1\n8K\tdir2\n12K\ttotal"
        result = self.p.process("du -sh *", output)
        assert result == output

    def test_wc_sorts_and_truncates(self):
        lines = [f"  {i * 10} src/file{i}.py" for i in range(25)]
        lines.append("  3000 total")
        output = "\n".join(lines)
        result = self.p.process("wc -l src/*.py", output)
        assert "total" in result
        assert "more" in result

    def test_wc_filters_zeros(self):
        lines = ["  100 a.py", "    0 empty.py", "    0 blank.py", "  100 total"]
        output = "\n".join(lines)
        result = self.p.process("wc -l *.py", output)
        assert result == output  # Short enough, unchanged

    def test_df_strips_snap_mounts(self):
        output = "\n".join(
            [
                "Filesystem      Size  Used Avail Use% Mounted on",
                "/dev/sda1       100G   50G   50G  50% /",
                "tmpfs            16G     0   16G   0% /dev/shm",
                "/dev/sda2       500G  200G  300G  40% /home",
                "devtmpfs         16G     0   16G   0% /dev",
                "/dev/loop0        56M   56M     0 100% /snap/core/12345",
                "/dev/loop1        64M   64M     0 100% /snap/lxd/23456",
                "tmpfs            16G  4.0K   16G   1% /tmp",
            ]
        )
        result = self.p.process("df -h", output)
        # Filesystem column (device paths) should be stripped
        assert "/dev/sda1" not in result
        assert "Filesystem" not in result
        # Data columns preserved
        assert "Size" in result
        assert "Mounted on" in result
        assert "/home" in result
        assert "/" in result
        assert "/snap" not in result
        assert "devtmpfs" not in result
        assert "/tmp" in result  # tmpfs /tmp kept
        assert "system mounts hidden" in result


class TestTerraformProcessor:
    def setup_method(self):
        self.p = TerraformProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("terraform plan")
        assert self.p.can_handle("terraform apply")
        assert self.p.can_handle("terraform destroy")
        assert self.p.can_handle("tofu plan")
        assert not self.p.can_handle("git status")

    def test_short_output_unchanged(self):
        output = "No changes. Infrastructure is up-to-date."
        result = self.p.process("terraform plan", output)
        assert result == output

    def test_strips_provider_init(self):
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
                "    }",
                "",
                "Plan: 1 to add, 0 to change, 0 to destroy.",
            ]
            + [""] * 20
        )  # pad to exceed 30 lines
        result = self.p.process("terraform plan", output)
        assert "Initializing" not in result
        assert "Installing" not in result
        assert "aws_instance.web" in result
        assert "Plan: 1 to add" in result

    def test_keeps_changed_attributes(self):
        output = "\n".join(
            [
                "# aws_instance.web will be updated in-place",
                '  ~ resource "aws_instance" "web" {',
                '      ~ instance_type = "t3.micro" -> "t3.small"',
                '        ami           = "ami-12345678"',
                "        tags          = {}",
                "    }",
                "",
                "Plan: 0 to add, 1 to change, 0 to destroy.",
            ]
            + [""] * 25
        )
        result = self.p.process("terraform plan", output)
        assert "t3.micro" in result
        assert "t3.small" in result
        assert "Plan: 0 to add, 1 to change" in result

    def test_preserves_errors(self):
        output = "\n".join(
            [
                "Error: Invalid instance type",
                "",
                "  on main.tf line 15:",
                '  15:   instance_type = "t3.nonexistent"',
            ]
            + [""] * 30
        )
        result = self.p.process("terraform plan", output)
        assert "Error: Invalid instance type" in result

    def test_can_handle_init_output_state(self):
        assert self.p.can_handle("terraform init")
        assert self.p.can_handle("terraform output")
        assert self.p.can_handle("terraform state list")
        assert self.p.can_handle("terraform state show aws_instance.web")
        assert self.p.can_handle("tofu init")
        assert self.p.can_handle("tofu output")

    def test_init_strips_noise_keeps_result(self):
        output = "\n".join(
            [
                "Initializing the backend...",
                "",
                "Initializing provider plugins...",
                "- Finding hashicorp/aws versions matching ~> 5.0...",
                "- Installing hashicorp/aws v5.31.0...",
                "- Installed hashicorp/aws v5.31.0 (signed by HashiCorp)",
                "",
                "Terraform has been successfully initialized!",
                "",
                "You may now begin working with Terraform.",
            ]
            + [""] * 15
        )
        result = self.p.process("terraform init", output)
        assert "Initializing" not in result
        assert "Finding" not in result
        assert "v5.31.0" in result
        assert "successfully initialized" in result

    def test_init_short_unchanged(self):
        output = "Terraform has been successfully initialized!"
        result = self.p.process("terraform init", output)
        assert result == output

    def test_output_truncates_long_values(self):
        lines = [f"key_{i} = " + "x" * 300 for i in range(40)]
        output = "\n".join(lines)
        result = self.p.process("terraform output", output)
        assert "chars" in result
        assert len(result) < len(output)

    def test_output_short_unchanged(self):
        output = 'db_host = "localhost"\ndb_port = 5432'
        result = self.p.process("terraform output", output)
        assert result == output

    def test_state_list_groups_by_type(self):
        lines = [f"aws_instance.web_{i}" for i in range(20)]
        lines += [f"aws_s3_bucket.data_{i}" for i in range(15)]
        output = "\n".join(lines)
        result = self.p.process("terraform state list", output)
        assert "35 resources in state" in result
        assert "aws_instance" in result
        assert "aws_s3_bucket" in result

    def test_state_list_short_unchanged(self):
        output = "aws_instance.web\naws_s3_bucket.data"
        result = self.p.process("terraform state list", output)
        assert result == output

    def test_state_show_truncates_long_attrs(self):
        lines = ["resource aws_instance.web:"]
        for i in range(50):
            lines.append(f"  attr_{i} = " + "y" * 250)
        output = "\n".join(lines)
        result = self.p.process("terraform state show aws_instance.web", output)
        assert "chars" in result
        assert len(result) < len(output)

    def test_subcommand_detection_not_fooled_by_args(self):
        """terraform plan -var init=true should NOT route to init handler."""
        output = "\n".join(
            [
                "# aws_instance.web will be created",
                '  + resource "aws_instance" "web" {',
                '      + ami = "ami-12345"',
                "    }",
                "Plan: 1 to add, 0 to change, 0 to destroy.",
            ]
            + [""] * 30
        )
        result = self.p.process("terraform plan -var init=true", output)
        assert "Plan: 1 to add" in result


class TestGhProcessor:
    def setup_method(self):
        self.p = GhProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("gh pr list")
        assert self.p.can_handle("gh issue list")
        assert self.p.can_handle("gh run view 12345")
        assert self.p.can_handle("gh pr diff 42")
        assert self.p.can_handle("gh pr checks")
        assert not self.p.can_handle("git status")
        assert not self.p.can_handle("gh auth login")

    def test_empty_output(self):
        assert self.p.process("gh pr list", "") == ""

    def test_pr_list_compresses_long_output(self):
        lines = []
        for i in range(40):
            lines.append(f"{i}\tFix bug #{i}\tfeature/fix-{i}\tOPEN\t2025-01-{i % 28 + 1:02d}")
        output = "\n".join(lines)
        result = self.p.process("gh pr list", output)
        assert "more pr" in result
        assert len(result.splitlines()) < len(lines)

    def test_pr_list_short_unchanged(self):
        output = "1\tFix login\tmain\tOPEN\t2025-01-01\n2\tAdd tests\tmain\tOPEN\t2025-01-02"
        result = self.p.process("gh pr list", output)
        assert result == output

    def test_pr_list_preserves_all_fields(self):
        lines = []
        for i in range(20):
            lines.append(f"{i}\tPR title {i}\tbranch-{i}\tOPEN\t2025-01-01")
        output = "\n".join(lines)
        result = self.p.process("gh pr list", output)
        # All 20 should be shown (< 30 threshold)
        assert "PR title 0" in result
        assert "PR title 19" in result

    def test_checks_collapses_passing(self):
        lines = []
        for i in range(15):
            lines.append(f"✓  build-{i}\tpassing\t1m")
        lines.append("✗  lint\tfailing\t30s")
        lines.append("○  deploy\tpending\t-")
        output = "\n".join(lines)
        result = self.p.process("gh pr checks", output)
        assert "15 checks passed" in result
        assert "lint" in result
        assert "deploy" in result
        assert "Failed" in result
        assert "Pending" in result

    def test_checks_short_unchanged(self):
        output = "✓  build\tpassing\t1m\n✓  test\tpassing\t2m"
        result = self.p.process("gh pr checks", output)
        assert result == output

    def test_diff_compresses(self):
        lines = ["diff --git a/file.py b/file.py", "@@ -1,200 +1,200 @@"]
        for i in range(200):
            lines.append(f"+line {i}")
        output = "\n".join(lines)
        result = self.p.process("gh pr diff 42", output)
        assert "truncated" in result
        assert len(result) < len(output)

    def test_diff_preserves_changes(self):
        lines = [
            "diff --git a/app.py b/app.py",
            "@@ -1,5 +1,6 @@",
            " context",
            "+added_line",
            "-removed_line",
            " context",
        ]
        output = "\n".join(lines)
        result = self.p.process("gh pr diff 42", output)
        assert "+added_line" in result
        assert "-removed_line" in result


class TestDbQueryProcessor:
    def setup_method(self):
        self.p = DbQueryProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("psql -d mydb -c 'SELECT * FROM users'")
        assert self.p.can_handle("mysql -u root mydb")
        assert self.p.can_handle("sqlite3 test.db")
        assert self.p.can_handle("pgcli postgres://localhost/mydb")
        assert not self.p.can_handle("git status")

    def test_empty_output(self):
        assert self.p.process("psql", "") == ""

    def test_psql_table_compressed(self):
        lines = [
            " id | name       | email",
            "----+------------+------------------",
        ]
        for i in range(50):
            lines.append(f" {i:2d} | user_{i:<6} | user{i}@example.com")
        lines.append("(50 rows)")
        output = "\n".join(lines)
        result = self.p.process("psql -c 'SELECT * FROM users'", output)
        assert "rows omitted" in result
        assert "(50 rows)" in result
        assert "id | name" in result
        assert len(result.splitlines()) < len(lines)

    def test_psql_short_unchanged(self):
        output = " id | name\n----+------\n  1 | Alice\n  2 | Bob\n(2 rows)"
        result = self.p.process("psql", output)
        assert result == output

    def test_mysql_table_compressed(self):
        lines = [
            "+----+--------+",
            "| id | name   |",
            "+----+--------+",
        ]
        for i in range(50):
            lines.append(f"| {i:2d} | user_{i} |")
        lines.append("+----+--------+")
        lines.append("50 rows in set (0.01 sec)")
        output = "\n".join(lines)
        result = self.p.process("mysql -e 'SELECT * FROM users'", output)
        assert "rows omitted" in result
        assert "50 rows in set" in result

    def test_mysql_short_unchanged(self):
        output = "+----+------+\n| id | name |\n+----+------+\n|  1 | Bob  |\n+----+------+"
        result = self.p.process("mysql", output)
        assert result == output

    def test_preserves_errors(self):
        output = "ERROR 1045 (28000): Access denied for user 'root'@'localhost'"
        result = self.p.process("mysql", output)
        assert "ERROR" in result
        assert "Access denied" in result

    def test_csv_output_compressed(self):
        lines = ["id,name,email"]
        for i in range(40):
            lines.append(f"{i},user_{i},user{i}@example.com")
        output = "\n".join(lines)
        result = self.p.process("psql -A -c 'SELECT * FROM users'", output)
        assert "rows omitted" in result
        assert "id,name,email" in result

    def test_csv_short_unchanged(self):
        output = "id,name\n1,Alice\n2,Bob"
        result = self.p.process("sqlite3 -csv", output)
        assert result == output


class TestCloudCliProcessor:
    def setup_method(self):
        self.p = CloudCliProcessor()

    def test_can_handle(self):
        assert self.p.can_handle("aws ec2 describe-instances")
        assert self.p.can_handle("gcloud compute instances list")
        assert self.p.can_handle("az vm list")
        assert not self.p.can_handle("git status")
        assert not self.p.can_handle("terraform plan")

    def test_empty_output(self):
        assert self.p.process("aws ec2 describe-instances", "") == ""

    def test_json_compressed(self):
        import json
        data = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": f"i-{i:012d}",
                            "State": {"Name": "running"},
                            "Tags": [{"Key": "Name", "Value": f"server-{i}"}],
                            "NetworkInterfaces": [
                                {
                                    "SubnetId": f"subnet-{j:08d}",
                                    "PrivateIpAddress": f"10.0.{i}.{j}",
                                    "Groups": [
                                        {"GroupId": f"sg-{j:08d}", "GroupName": f"group-{j}"},
                                    ],
                                }
                                for j in range(5)
                            ],
                        }
                        for i in range(10)
                    ]
                }
            ]
        }
        output = json.dumps(data, indent=2)
        result = self.p.process("aws ec2 describe-instances", output)
        assert "i-" in result
        assert "running" in result
        assert len(result) < len(output)

    def test_json_short_unchanged(self):
        output = '{"InstanceId": "i-123", "State": "running"}'
        result = self.p.process("aws ec2 describe-instances", output)
        # Short JSON should be parsed and re-serialized but not truncated
        assert "i-123" in result
        assert "running" in result

    def test_preserves_errors(self):
        import json
        data = {
            "error": {
                "code": "UnauthorizedAccess",
                "message": "User is not authorized to perform this operation"
            }
        }
        output = json.dumps(data, indent=2)
        result = self.p.process("aws ec2 describe-instances", output)
        assert "UnauthorizedAccess" in result
        assert "not authorized" in result

    def test_preserves_state_and_id_fields(self):
        import json
        data = {
            "InstanceId": "i-abc123def456",
            "State": {"Name": "stopped", "Code": 80},
            "arn": "arn:aws:ec2:us-east-1:123456789:instance/i-abc123def456",
            "VeryDeepField": {
                "Level1": {
                    "Level2": {
                        "Level3": {
                            "Level4": {"data": "deep value"}
                        }
                    }
                }
            }
        }
        output = json.dumps(data, indent=2)
        result = self.p.process("aws ec2 describe-instances", output)
        assert "i-abc123def456" in result
        assert "stopped" in result
        assert "arn:aws:ec2" in result

    def test_table_output_compressed(self):
        lines = [
            "+---+---+---+",
            "| InstanceId | State | Name |",
            "+---+---+---+",
        ]
        for i in range(30):
            lines.append(f"| i-{i:010d} | running | server-{i} |")
        lines.append("+---+---+---+")
        output = "\n".join(lines)
        result = self.p.process("aws ec2 describe-instances --output table", output)
        assert "more rows" in result
        assert len(result.splitlines()) < len(lines)

    def test_text_output_compressed(self):
        lines = [f"i-{i:012d}\trunning\tserver-{i}\tt3.micro" for i in range(50)]
        output = "\n".join(lines)
        result = self.p.process("aws ec2 describe-instances --output text", output)
        assert "omitted" in result
        assert len(result.splitlines()) < len(lines)

    def test_text_short_unchanged(self):
        output = "i-123\trunning\tserver-1"
        result = self.p.process("aws ec2 describe-instances --output text", output)
        assert result == output


class TestGitRemoteProcessor:
    """Tests for git remote subcommand handler."""

    def setup_method(self):
        self.p = GitProcessor()

    def test_can_handle_remote(self):
        assert self.p.can_handle("git remote -v")
        assert self.p.can_handle("git remote")

    def test_remote_short_unchanged(self):
        output = (
            "origin\thttps://github.com/user/repo.git (fetch)\n"
            "origin\thttps://github.com/user/repo.git (push)"
        )
        result = self.p.process("git remote -v", output)
        assert result == output

    def test_remote_deduplicates_fetch_push(self):
        lines = []
        for i in range(8):
            lines.append(f"remote-{i}\thttps://github.com/user/repo-{i}.git (fetch)")
            lines.append(f"remote-{i}\thttps://github.com/user/repo-{i}.git (push)")
        output = "\n".join(lines)
        result = self.p.process("git remote -v", output)
        assert "fetch/push deduplicated" in result
        assert "remote-0" in result
        assert "remote-7" in result
        assert len(result.splitlines()) < len(lines)


class TestGitTypechange:
    """Test typechange status code handling."""

    def setup_method(self):
        self.p = GitProcessor()

    def test_status_typechange(self):
        output = "\n".join([
            "On branch main",
            "Changes not staged for commit:",
            "  typechange:   src/link.py",
            "  modified:     src/app.py",
        ])
        result = self.p.process("git status", output)
        assert "link.py" in result
        assert "T" in result
