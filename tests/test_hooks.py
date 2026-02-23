"""Tests for hooks and wrapper."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude.hook_pretool import is_compressible


class TestHookPretool:
    def test_git_commands_compressible(self):
        assert is_compressible("git status")
        assert is_compressible("git diff --cached")
        assert is_compressible("git log --oneline -20")
        assert is_compressible("git push origin main")
        assert is_compressible("git pull")
        assert is_compressible("git fetch --all")
        assert is_compressible("git reflog")

    def test_git_global_options_compressible(self):
        assert is_compressible("git -C /some/path status")
        assert is_compressible("git -C /opt/homebrew log --oneline -20")
        assert is_compressible("git --no-pager diff HEAD~1")
        assert is_compressible("git -C /path --no-pager log")
        assert is_compressible("git --no-pager -C /path status")
        assert is_compressible("git -c core.pager=cat log --oneline")
        assert is_compressible("git --git-dir=/path/.git status")
        assert is_compressible("git --work-tree /path status")

    def test_test_commands_compressible(self):
        assert is_compressible("pytest tests/")
        assert is_compressible("python -m pytest")
        assert is_compressible("python3 -m pytest -v")
        assert is_compressible("jest --coverage")
        assert is_compressible("cargo test")
        assert is_compressible("go test ./...")
        assert is_compressible("npm test")
        assert is_compressible("bun test")

    def test_build_commands_compressible(self):
        assert is_compressible("npm run build")
        assert is_compressible("npm install")
        assert is_compressible("cargo build")
        assert is_compressible("make")
        assert is_compressible("pip install -r requirements.txt")
        assert is_compressible("tsc")
        assert is_compressible("webpack")
        assert is_compressible("next build")

    def test_lint_commands_compressible(self):
        assert is_compressible("eslint src/")
        assert is_compressible("ruff check .")
        assert is_compressible("ruff .")
        assert is_compressible("pylint src/")
        assert is_compressible("python3 -m mypy src/")

    def test_file_commands_compressible(self):
        assert is_compressible("ls -la")
        assert is_compressible("find . -name '*.py'")
        assert is_compressible("tree src/")
        assert is_compressible("cat file.py")

    def test_complex_pipelines_excluded(self):
        assert not is_compressible("cat file.txt | sort | uniq")
        assert not is_compressible("git log | grep fix | sort")
        assert not is_compressible("git log | grep fix | wc -l")
        assert not is_compressible("cat app.log | tail -100 | grep ERROR")
        assert not is_compressible("ls | awk '{print $1}'")
        assert not is_compressible("git log | sed 's/foo/bar/'")
        assert not is_compressible("find . | xargs rm")

    def test_safe_trailing_truncation_pipes(self):
        """head, tail, wc after a compressible command."""
        assert is_compressible("git status | head")
        assert is_compressible("git log --oneline | tail -20")
        assert is_compressible("pip3 list | head -30")
        assert is_compressible("ls -la /tmp | wc -l")
        assert is_compressible("pytest tests/ | tail -10")
        assert is_compressible("git log --oneline | head -n 50")
        assert is_compressible("find . -name '*.py' | wc -l")

    def test_safe_trailing_grep_pipes(self):
        """Single grep filter after a compressible command."""
        assert is_compressible("git log --oneline | grep fix")
        assert is_compressible("pip3 list | grep -i torch")
        assert is_compressible("docker ps | grep running")
        assert is_compressible("git log --oneline | grep -v Merge")
        assert is_compressible("ls -la | grep .py")
        assert is_compressible("pip list | grep -E 'torch|numpy'")
        assert is_compressible("git log | grep -c fix")

    def test_safe_trailing_sort_uniq_cut_pipes(self):
        """sort, uniq, cut after a compressible command."""
        assert is_compressible("docker ps | sort")
        assert is_compressible("docker ps | sort -k 2")
        assert is_compressible("find . -name '*.py' | sort -r")
        assert is_compressible("pip list | uniq")
        assert is_compressible("pip list | uniq -c")
        assert is_compressible("ls -la | cut -f1 -d,")

    def test_or_chains_excluded(self):
        assert not is_compressible("make || echo failed")

    def test_interactive_commands_excluded(self):
        assert not is_compressible("vim file.py")
        assert not is_compressible("nano file.py")
        assert not is_compressible("ssh server")

    def test_self_wrapping_excluded(self):
        assert not is_compressible("python3 wrap.py git status")
        assert not is_compressible("python3 /path/to/token_saver/wrap.py ls")
        assert not is_compressible("token-saver stats")

    def test_token_saver_in_path_not_excluded(self):
        """token-saver in a path argument must not trigger the self-wrap guard."""
        assert is_compressible("ls /Users/user/Desktop/token-saver")
        assert is_compressible("git -C /path/token-saver status")
        assert is_compressible("cat /tmp/token-saver/README.md")

    def test_sudo_excluded(self):
        assert not is_compressible("sudo apt install foo")

    def test_redirections_excluded(self):
        assert not is_compressible("git log > log.txt")

    def test_empty_command(self):
        assert not is_compressible("")
        assert not is_compressible("   ")

    def test_unknown_commands_not_compressible(self):
        assert not is_compressible("echo hello")
        assert not is_compressible("python3 script.py")
        assert not is_compressible("cp file1 file2")

    def test_docker_commands_compressible(self):
        assert is_compressible("docker build .")
        assert is_compressible("docker ps")
        assert is_compressible("docker logs container")

    def test_docker_global_options_compressible(self):
        assert is_compressible("docker --context remote ps")
        assert is_compressible("docker -H tcp://host:2375 ps")
        assert is_compressible("docker --host unix:///var/run/docker.sock images")

    def test_network_commands_compressible(self):
        assert is_compressible("curl https://example.com")
        assert is_compressible("curl -v https://api.example.com/data")
        assert is_compressible("wget https://example.com/file.tar.gz")

    def test_kubectl_commands_compressible(self):
        assert is_compressible("kubectl get pods")
        assert is_compressible("kubectl describe pod my-pod")
        assert is_compressible("kubectl logs my-pod")

    def test_kubectl_global_options_compressible(self):
        assert is_compressible("kubectl -n kube-system get pods")
        assert is_compressible("kubectl --namespace kube-system get pods")
        assert is_compressible("kubectl --context prod get nodes")
        assert is_compressible("kubectl -A get pods")
        assert is_compressible("kubectl --all-namespaces get pods")
        assert is_compressible("kubectl -n monitoring --context staging describe pod my-pod")
        assert is_compressible("kubectl --kubeconfig /path/config get svc")

    def test_terraform_commands_compressible(self):
        assert is_compressible("terraform plan")
        assert is_compressible("terraform apply")
        assert is_compressible("tofu plan")

    def test_env_commands_compressible(self):
        assert is_compressible("env")
        assert is_compressible("printenv")

    def test_env_prefix_excluded(self):
        assert not is_compressible("env FOO=bar command")

    def test_package_list_commands_compressible(self):
        assert is_compressible("pip list")
        assert is_compressible("pip3 list")
        assert is_compressible("pip freeze")
        assert is_compressible("npm ls")
        assert is_compressible("npm list")
        assert is_compressible("conda list")

    def test_grep_commands_compressible(self):
        assert is_compressible("grep -r pattern .")
        assert is_compressible("rg pattern")
        assert is_compressible("ag pattern src/")

    def test_system_info_commands_compressible(self):
        assert is_compressible("du -sh *")
        assert is_compressible("wc -l *.py")
        assert is_compressible("df -h")

    def test_new_test_runners_compressible(self):
        assert is_compressible("pnpm test")
        assert is_compressible("yarn test")
        assert is_compressible("dotnet test")
        assert is_compressible("swift test")
        assert is_compressible("mix test")
        assert is_compressible("vitest")
        assert is_compressible("bun test")

    def test_new_git_subcommands_compressible(self):
        assert is_compressible("git blame src/main.py")
        assert is_compressible("git cherry-pick abc123")
        assert is_compressible("git rebase main")
        assert is_compressible("git merge feature/branch")
        assert is_compressible("git stash list")

    def test_new_lint_commands_compressible(self):
        assert is_compressible("mypy src/")
        assert is_compressible("shellcheck script.sh")
        assert is_compressible("hadolint Dockerfile")
        assert is_compressible("cargo clippy")
        assert is_compressible("prettier --check src/")
        assert is_compressible("biome check src/")
        assert is_compressible("biome lint src/")

    def test_new_docker_subcommands_compressible(self):
        assert is_compressible("docker inspect container")
        assert is_compressible("docker stats")
        assert is_compressible("docker compose up -d")
        assert is_compressible("docker compose down")
        assert is_compressible("docker compose build")
        assert is_compressible("docker compose ps")
        assert is_compressible("docker compose logs web")

    def test_new_kubectl_subcommands_compressible(self):
        assert is_compressible("kubectl apply -f deployment.yaml")
        assert is_compressible("kubectl delete pod my-pod")
        assert is_compressible("kubectl create namespace test")

    def test_new_terraform_subcommands_compressible(self):
        assert is_compressible("terraform init")
        assert is_compressible("terraform output")
        assert is_compressible("terraform state list")
        assert is_compressible("terraform state show aws_instance.web")
        assert is_compressible("tofu init")
        assert is_compressible("tofu output")

    def test_new_build_commands_compressible(self):
        assert is_compressible("turbo run build")
        assert is_compressible("turbo build")
        assert is_compressible("nx run build")
        assert is_compressible("nx build")
        assert is_compressible("docker compose build")

    def test_new_search_commands_compressible(self):
        assert is_compressible("fd -e py")
        assert is_compressible("fdfind pattern")

    def test_new_file_listing_commands_compressible(self):
        assert is_compressible("exa -la")
        assert is_compressible("eza --long")

    def test_httpie_compressible(self):
        assert is_compressible("http GET https://api.example.com")
        assert is_compressible("https POST https://api.example.com")


class TestHookPretoolIntegration:
    """Test the full hook script behavior via subprocess."""

    def _run_hook(self, input_data: dict) -> tuple[str, int]:
        """Run hook_pretool.py with JSON input, return (stdout, exit_code)."""
        import subprocess

        hook_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hook_pretool.py"
        )
        result = subprocess.run(  # noqa: S603, PLW1510
            [sys.executable, hook_path],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout, result.returncode

    def test_bash_git_status_rewritten(self):
        stdout, code = self._run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        )
        assert code == 0
        data = json.loads(stdout)
        cmd = data["hookSpecificOutput"]["updatedInput"]["command"]
        assert "wrap.py" in cmd
        assert "git status" in cmd

    def test_non_bash_tool_passthrough(self):
        stdout, code = self._run_hook({"tool_name": "Read", "tool_input": {"path": "/some/file"}})
        assert code == 0
        assert stdout == ""

    def test_non_compressible_passthrough(self):
        stdout, code = self._run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "echo hello"}}
        )
        assert code == 0
        assert stdout == ""

    def test_invalid_json_exits_cleanly(self):
        import subprocess

        hook_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hook_pretool.py"
        )
        result = subprocess.run(  # noqa: S603, PLW1510
            [sys.executable, hook_path],
            input="not json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    def test_command_properly_quoted(self):
        """Ensure shell metacharacters in commands are safely quoted."""
        stdout, code = self._run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git log --format='%H %s'"}}
        )
        assert code == 0
        if stdout:
            data = json.loads(stdout)
            cmd = data["hookSpecificOutput"]["updatedInput"]["command"]
            # Should be safely quoted
            assert "wrap.py" in cmd

    def test_piped_command_preserved_in_rewrite(self):
        """The full original command including pipe must be passed to wrap.py."""
        stdout, code = self._run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git log --oneline | grep fix"}}
        )
        assert code == 0
        assert stdout  # Should produce output (not empty passthrough)
        data = json.loads(stdout)
        rewritten = data["hookSpecificOutput"]["updatedInput"]["command"]
        assert "wrap.py" in rewritten
        # Full command including pipe must be inside the quoted argument
        assert "grep fix" in rewritten

    def test_multi_stage_pipe_not_rewritten(self):
        """Complex pipelines should NOT be rewritten."""
        stdout, code = self._run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git log | grep fix | wc -l"}}
        )
        assert code == 0
        assert stdout == ""  # Passthrough, no rewrite

    def test_session_id_embedded_in_rewrite(self):
        """Claude Code's session_id should be embedded as env var in rewritten command."""
        stdout, code = self._run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "session_id": "cc-session-xyz",
            }
        )
        assert code == 0
        data = json.loads(stdout)
        cmd = data["hookSpecificOutput"]["updatedInput"]["command"]
        assert "TOKEN_SAVER_SESSION=cc-session-xyz" in cmd
        assert "wrap.py" in cmd

    def test_no_session_id_still_works(self):
        """If no session_id in payload, command should still be rewritten (without prefix)."""
        stdout, code = self._run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        )
        assert code == 0
        data = json.loads(stdout)
        cmd = data["hookSpecificOutput"]["updatedInput"]["command"]
        assert "wrap.py" in cmd
        assert "TOKEN_SAVER_SESSION" not in cmd


class TestChainedCommands:
    """Tests for && and ; chained command support."""

    def test_all_compressible_and_chain(self):
        assert is_compressible("git add . && git commit -m fix && git push")
        assert is_compressible("git status && git diff")

    def test_silent_plus_compressible(self):
        assert is_compressible("cd /project && npm install")
        assert is_compressible("mkdir -p /tmp/test && ls -la /tmp/test")
        assert is_compressible("cd /project && git status")

    def test_all_silent_rejected(self):
        assert not is_compressible("cd /tmp && mkdir -p foo")
        assert not is_compressible("export FOO=bar && cd /tmp")

    def test_unknown_command_in_chain_rejected(self):
        assert not is_compressible("echo hello && git status")
        assert not is_compressible("git status && python3 script.py")

    def test_pipe_in_non_last_segment_rejected(self):
        assert not is_compressible("git status | grep foo && git diff")
        assert not is_compressible("cat file | sort && git status")

    def test_redirect_in_segment_rejected(self):
        assert not is_compressible("git status && git log > log.txt")

    def test_sudo_in_segment_rejected(self):
        assert not is_compressible("cd /project && sudo apt install foo")

    def test_or_chain_always_rejected(self):
        assert not is_compressible("git push || echo failed")
        assert not is_compressible("git add . && git push || echo failed")

    def test_semicolon_chains(self):
        assert is_compressible("cd /project; npm install")
        assert is_compressible("cd /tmp; ls -la")

    def test_mixed_and_semicolon(self):
        assert is_compressible("cd /project && git add .; git push")
        assert is_compressible("mkdir -p /tmp/test; cd /tmp/test && ls -la")

    def test_safe_trailing_pipe_on_last_segment(self):
        assert is_compressible("cd /project && git log --oneline | head -20")

    def test_self_wrap_guard_in_chain(self):
        assert not is_compressible("cd /project && python3 wrap.py git status")
        assert not is_compressible("cd /project && token-saver stats")

    # --- Real-world Claude Code patterns ---

    def test_real_world_git_add_commit_push(self):
        """The most common Claude Code chained command."""
        assert is_compressible("git add . && git commit -m 'feat: add auth' && git push")
        assert is_compressible('git add . && git commit -m "fix bug" && git push origin main')

    def test_real_world_cd_then_build(self):
        assert is_compressible("cd /project && npm run build")
        assert is_compressible("cd /project && cargo build")
        assert is_compressible("cd /project && make")

    def test_real_world_cd_then_test(self):
        assert is_compressible("cd /project && npm test")
        assert is_compressible("cd /project && pytest tests/ -v")
        assert is_compressible("cd /project && cargo test")

    def test_real_world_mkdir_then_ls(self):
        assert is_compressible("mkdir -p /tmp/output && ls -la /tmp/output")

    def test_real_world_cd_then_lint(self):
        assert is_compressible("cd /project && ruff check .")
        assert is_compressible("cd /project && eslint src/")

    def test_real_world_git_stash_then_pull(self):
        assert is_compressible("git stash && git pull")

    def test_real_world_checkout_then_status(self):
        """git checkout is silent, git status is compressible."""
        assert is_compressible("git checkout main && git status")
        assert is_compressible("git checkout -b feature && git status")

    def test_real_world_multi_silent_then_compressible(self):
        assert is_compressible("cd /project && git checkout main && git pull")
        assert is_compressible("mkdir -p dist && cp src/*.py dist/ && ls -la dist/")

    def test_real_world_terraform_init_plan(self):
        assert is_compressible("cd infra && terraform init && terraform plan")

    def test_real_world_docker_compose(self):
        assert is_compressible("cd /app && docker compose build && docker compose up -d")

    # --- Quoted delimiters (should NOT split) ---

    def test_quoted_semicolon_not_split(self):
        """A ; inside quotes is not a chain delimiter."""
        assert is_compressible("grep -r 'foo;bar' .")
        assert is_compressible('grep -r "error; fatal" src/')

    def test_quoted_ampersand_not_split(self):
        """&& inside quotes is not a chain delimiter."""
        assert is_compressible('git log --format="%H && %s"')

    # --- Edge cases ---

    def test_env_var_in_chain_rejected(self):
        """env VAR=val prefix in any segment should reject the chain."""
        assert not is_compressible("cd /project && env FOO=bar npm test")

    def test_interactive_in_chain_rejected(self):
        assert not is_compressible("cd /project && vim file.py")
        assert not is_compressible("mkdir -p /tmp && ssh server")

    def test_safe_trailing_pipe_on_last_segment_various(self):
        assert is_compressible("cd /project && pip list | grep torch")
        assert is_compressible("cd /project && git log --oneline | tail -20")
        assert is_compressible("cd /project && docker ps | wc -l")

    def test_single_segment_after_split(self):
        """A command with quoted ; shouldn't change single-command behavior."""
        assert is_compressible("git status")
        assert not is_compressible("echo hello")

    def test_three_segment_chain(self):
        assert is_compressible("cd /a && cd /b && git status")
        assert is_compressible("touch f && chmod 644 f && ls -la f")
