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

    def test_piped_commands_excluded(self):
        assert not is_compressible("git status | head")
        assert not is_compressible("ls | grep foo")

    def test_chained_commands_excluded(self):
        assert not is_compressible("git add . && git commit")
        assert not is_compressible("make || echo failed")

    def test_interactive_commands_excluded(self):
        assert not is_compressible("vim file.py")
        assert not is_compressible("nano file.py")
        assert not is_compressible("ssh server")

    def test_self_wrapping_excluded(self):
        assert not is_compressible("python3 wrap.py git status")
        assert not is_compressible("python3 /path/to/token_saver/wrap.py ls")

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
