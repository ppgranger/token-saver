"""Realistic *failing* command output, one case per processor.

These exist to enforce the project's central promise — "never lose critical
information" — as a mechanical invariant rather than a per-processor
convention.  Each case is the output of a command that failed, long enough to
trigger compression, with the reason for the failure sitting somewhere in the
middle where naive head+tail truncation would drop it.

``tests/test_precision.py::TestFailureHandling`` runs every case through the
real engine and asserts the failure reason survives.
"""

from __future__ import annotations

from typing import NamedTuple


class FailureCase(NamedTuple):
    """A failed command, its output, and the text that must never be lost."""

    processor: str
    command: str
    output: str
    critical: tuple[str, ...]


def _pad(line_template: str, count: int, start: int = 0) -> list[str]:
    """Generate ``count`` lines of plausible, uninteresting output."""
    return [line_template.format(i=i) for i in range(start, start + count)]


def _build(head: list[str], filler: list[str], reason: list[str], tail: list[str]) -> str:
    """Assemble an output with the failure reason buried in the middle."""
    return "\n".join([*head, *filler, *reason, *filler, *tail])


CASES: list[FailureCase] = [
    FailureCase(
        "package_list",
        "pip list",
        _build(
            ["Package    Version", "---------- -------"],
            _pad("pkg{i}      1.0.{i}", 40),
            ["ERROR: pip's dependency resolver does not currently take into account"],
            ["urllib3    2.2.1"],
        ),
        ("ERROR: pip's dependency resolver",),
    ),
    FailureCase(
        "just",
        "just --list",
        _build(
            ["Available recipes:"],
            _pad("    recipe{i}", 30),
            ["error: Justfile does not contain recipe `deploy`"],
            ["    test"],
        ),
        ("error: Justfile does not contain recipe",),
    ),
    FailureCase(
        "act",
        "act -j build",
        _build(
            ["[build/build] 🚀  Start image=catthehacker/ubuntu:act-latest"],
            _pad("[build/build]   ✅  Success - step {i}", 30),
            ["[build/build]   ❌  Failure - Main Run tests", "Error: exit with `FAILURE`: 1"],
            ["[build/build] 🏁  Job failed"],
        ),
        ("Failure - Main Run tests", "exit with `FAILURE`"),
    ),
    FailureCase(
        "git",
        "git merge feature",
        _build(
            ["Auto-merging src/app.py"],
            _pad("Auto-merging src/mod{i}.py", 40),
            ["CONFLICT (content): Merge conflict in src/core.py", "error: could not apply 3f2a1b9"],
            ["Automatic merge failed; fix conflicts and then commit the result."],
        ),
        ("CONFLICT (content): Merge conflict in src/core.py", "error: could not apply"),
    ),
    FailureCase(
        "test",
        "pytest tests/",
        _build(
            ["============================= test session starts ============================="],
            _pad("tests/test_mod{i}.py .................                             [ {i}%]", 40),
            [
                "================================== FAILURES ===================================",
                "_______________________________ test_migration ________________________________",
                "E       MigrationError: migration failed at step 3",
                "tests/test_db.py:87: MigrationError",
                "=========================== short test summary info ===========================",
                "FAILED tests/test_db.py::test_migration - MigrationError",
            ],
            ["=========================== 1 failed, 402 passed ==========================="],
        ),
        ("MigrationError: migration failed at step 3",),
    ),
    FailureCase(
        "cargo",
        "cargo build",
        _build(
            ["   Compiling myapp v0.1.0 (/src)"],
            _pad("   Compiling dep{i} v1.0.{i}", 40),
            [
                "error[E0308]: mismatched types",
                "  --> src/main.rs:42:18",
                "   |",
                '42 |     let x: u32 = "hello";',
                "   |            ---   ^^^^^^^ expected `u32`, found `&str`",
            ],
            ['error: could not compile `myapp` (bin "myapp") due to 1 previous error'],
        ),
        ("error[E0308]: mismatched types", "could not compile `myapp`"),
    ),
    FailureCase(
        "go",
        "go build ./...",
        _build(
            ["go: downloading github.com/pkg/errors v0.9.1"],
            _pad("go: downloading example.com/mod{i} v1.0.{i}", 40),
            ["./handler.go:31:9: undefined: computeChecksum"],
            ["FAIL\tgithub.com/acme/api [build failed]"],
        ),
        ("undefined: computeChecksum",),
    ),
    FailureCase(
        "python_install",
        "pip install -r requirements.txt",
        _build(
            ["Collecting flask"],
            _pad("Collecting dep{i}", 40),
            [
                "ERROR: Could not find a version that satisfies the requirement torch==9.9.9",
                "ERROR: No matching distribution found for torch==9.9.9",
            ],
            ["[notice] A new release of pip is available"],
        ),
        ("No matching distribution found for torch==9.9.9",),
    ),
    FailureCase(
        "build",
        "npm run build",
        _build(
            ["> myapp@1.0.0 build", "> webpack --mode production"],
            _pad("asset chunk{i}.js 12.{i} KiB [emitted]", 40),
            [
                "ERROR in ./src/index.js 14:0-32",
                "Module not found: Error: Can't resolve './missing' in '/src'",
            ],
            ["webpack 5.90.0 compiled with 1 error"],
        ),
        ("Module not found: Error: Can't resolve './missing'",),
    ),
    FailureCase(
        "cargo_clippy",
        "cargo clippy",
        _build(
            ["    Checking myapp v0.1.0"],
            _pad("warning: unused variable: `x{i}`", 30),
            [
                "error: this operation will panic at runtime",
                "  --> src/lib.rs:12:5",
                "   |",
                "12 |     arr[99]",
            ],
            ["error: could not compile `myapp` due to 1 previous error"],
        ),
        ("this operation will panic at runtime",),
    ),
    FailureCase(
        "lint",
        "eslint src/",
        _build(
            ["/src/a.js"],
            _pad("  {i}:1  warning  Unexpected console statement  no-console", 40),
            ["  87:3  error  'fetchUser' is not defined  no-undef"],
            ["✖ 41 problems (1 error, 40 warnings)"],
        ),
        ("'fetchUser' is not defined",),
    ),
    FailureCase(
        "maven_gradle",
        "mvn package",
        _build(
            ["[INFO] Scanning for projects..."],
            _pad("[INFO] Compiling source file {i}", 40),
            [
                "[ERROR] /src/Main.java:[21,9] cannot find symbol",
                "[ERROR]   symbol:   method compute()",
            ],
            ["[INFO] BUILD FAILURE"],
        ),
        ("cannot find symbol",),
    ),
    FailureCase(
        # NB: `bun install` is claimed by the build processor (priority 25,
        # ahead of bun's 29) — `bun add` is what actually reaches this one.
        "bun",
        "bun add @acme/private-pkg",
        _build(
            ["bun add v1.1.0"],
            _pad(" + pkg{i}@1.0.{i}", 40),
            ["error: FileNotFound installing @acme/private-pkg"],
            [" 40 packages installed [1.20s]"],
        ),
        ("FileNotFound installing @acme/private-pkg",),
    ),
    FailureCase(
        "network",
        "curl -v https://api.example.com/v1/items",
        _build(
            ["* Trying 93.184.216.34:443..."],
            _pad("< x-custom-header-{i}: value{i}", 30),
            ["< HTTP/2 503", "< x-error-reason: upstream connection refused"],
            ["* Connection #0 to host api.example.com left intact"],
        ),
        ("503",),
    ),
    FailureCase(
        # `docker build` is claimed by the build processor; `docker pull` is
        # what routes here.
        "docker",
        "docker pull acme/app:latest",
        _build(
            ["latest: Pulling from acme/app"],
            _pad("a1b2c3d{i}: Pulling fs layer", 40),
            ["error pulling image configuration: unauthorized: authentication required"],
            ["ERROR: failed to pull image acme/app:latest"],
        ),
        ("unauthorized: authentication required",),
    ),
    FailureCase(
        "kubectl",
        "kubectl apply -f manifests/",
        _build(
            ["deployment.apps/api configured"],
            _pad("configmap/cfg{i} unchanged", 40),
            [
                'Error from server (Invalid): error when creating "svc.yaml": '
                'Service in version "v1" cannot be handled'
            ],
            ["service/web unchanged"],
        ),
        ("Error from server (Invalid)",),
    ),
    FailureCase(
        "terraform",
        "terraform apply",
        _build(
            ["Terraform used the selected providers to generate the following execution plan."],
            _pad("  # aws_instance.node{i} will be created", 40),
            [
                "Error: creating EC2 Instance: InvalidParameterValue: "
                "Value () for parameter groupId is invalid",
            ],
            ["Apply complete! Resources: 0 added, 0 changed, 0 destroyed."],
        ),
        ("InvalidParameterValue",),
    ),
    FailureCase(
        "env",
        "env",
        _build(
            ["SHELL=/bin/zsh"],
            _pad("VAR{i}=value{i}", 40),
            ["LAST_COMMAND_ERROR=deployment failed: permission denied"],
            ["TERM=xterm-256color"],
        ),
        ("permission denied",),
    ),
    FailureCase(
        "search",
        "grep -rn TODO src/",
        _build(
            ["src/a.py:12:# TODO refactor"],
            _pad("src/mod{i}.py:{i}:# TODO item {i}", 40),
            ["grep: src/private: Permission denied"],
            ["src/z.py:99:# TODO last"],
        ),
        ("Permission denied",),
    ),
    FailureCase(
        "system_info",
        "du -sh /var/*",
        _build(
            ["4.0K\t/var/empty"],
            _pad("{i}M\t/var/dir{i}", 40),
            ["du: cannot read directory '/var/root': Permission denied"],
            ["1.2G\t/var/log"],
        ),
        ("Permission denied",),
    ),
    FailureCase(
        "gh",
        "gh run list",
        _build(
            ["completed  success  build  main  push  1001"],
            _pad("completed  success  test{i}  main  push  10{i}", 40),
            ["completed  failure  deploy  main  push  1099"],
            ["completed  success  lint  main  push  1100"],
        ),
        ("failure",),
    ),
    FailureCase(
        "db_query",
        "psql -c 'SELECT * FROM users'",
        _build(
            [" id | name", "----+------"],
            _pad("  {i} | user{i}", 40),
            [
                'ERROR:  relation "users" does not exist',
                "LINE 1: SELECT * FROM users",
            ],
            ["(40 rows)"],
        ),
        ('relation "users" does not exist',),
    ),
    FailureCase(
        "cloud_cli",
        "aws s3 ls s3://bucket",
        _build(
            ["2024-01-01 10:00:00  1024 file0.txt"],
            _pad("2024-01-01 10:00:00  10{i} file{i}.txt", 40),
            [
                "An error occurred (AccessDenied) when calling the ListObjectsV2 operation: "
                "Access Denied"
            ],
            ["2024-06-01 10:00:00  2048 last.txt"],
        ),
        ("AccessDenied",),
    ),
    FailureCase(
        "ansible",
        "ansible-playbook site.yml",
        _build(
            ["PLAY [webservers] **************************************************"],
            _pad("ok: [host{i}]", 40),
            [
                'fatal: [web03]: FAILED! => {"changed": false, '
                '"msg": "Unable to start service nginx: job failed"}'
            ],
            ["PLAY RECAP *********************************************************"],
        ),
        ("Unable to start service nginx",),
    ),
    FailureCase(
        "helm",
        "helm upgrade api ./chart",
        _build(
            ['Release "api" has been upgraded. Happy Helming!'],
            _pad("NOTES line {i}", 40),
            ['Error: UPGRADE FAILED: cannot patch "api" with kind Deployment: field is immutable'],
            ["REVISION: 12"],
        ),
        ("UPGRADE FAILED",),
    ),
    FailureCase(
        "syslog",
        "journalctl -u api",
        _build(
            ["-- Journal begins at Mon 2024-01-01 --"],
            _pad("Jan 01 10:00:{i} host api[123]: request handled", 40),
            ["Jan 01 10:05:00 host api[123]: FATAL: could not bind to port 8080"],
            ["Jan 01 10:06:00 host systemd[1]: api.service: Main process exited"],
        ),
        ("could not bind to port 8080",),
    ),
    FailureCase(
        "ssh",
        "scp file.txt host:/tmp/",
        _build(
            ["file.txt   0%    0     0.0KB/s   --:-- ETA"],
            _pad("file.txt  {i}%  10{i}KB   1.0MB/s   00:0{i} ETA", 30),
            ["scp: /tmp/file.txt: Permission denied"],
            ["lost connection"],
        ),
        ("Permission denied",),
    ),
    FailureCase(
        "jq_yq",
        "jq '.items[]' data.json",
        _build(
            ["{"],
            _pad('  "field{i}": "value{i}",', 40),
            ['jq: error (at data.json:41): Cannot index string with "items"'],
            ["}"],
        ),
        ("Cannot index string",),
    ),
    FailureCase(
        "structured_log",
        "stern api",
        _build(
            ['{"level":"info","msg":"started"}'],
            _pad('{{"level":"info","msg":"handled request {i}"}}', 40),
            ['{"level":"error","msg":"payment gateway unreachable","code":502}'],
            ['{"level":"info","msg":"shutting down"}'],
        ),
        ("payment gateway unreachable",),
    ),
    FailureCase(
        "pulumi",
        "pulumi up",
        _build(
            ["Previewing update (dev)"],
            _pad("    + aws:s3:Bucket b{i} created", 40),
            ["error: 1 error occurred:", "    * creating bucket: BucketAlreadyExists"],
            ["Resources: 40 created"],
        ),
        ("BucketAlreadyExists",),
    ),
    FailureCase(
        "cdktf",
        "cdktf deploy",
        _build(
            ["Deploying stack: dev"],
            _pad("dev  aws_instance.node{i}  Creating...", 40),
            ["dev  Error: Invalid AMI ID: ami-deadbeef does not exist"],
            ["dev  Summary: 0 created, 0 updated, 0 destroyed."],
        ),
        ("Invalid AMI ID",),
    ),
    FailureCase(
        "nix",
        "nix build .#package",
        _build(
            ["these 3 derivations will be built:"],
            _pad("  /nix/store/hash{i}-dep{i}.drv", 40),
            [
                "error: builder for '/nix/store/xyz-app.drv' failed with exit code 1",
                "       last 1 log lines: > gcc: fatal error: no input files",
            ],
            ["error: build of '/nix/store/xyz-app.drv' failed"],
        ),
        ("no input files",),
    ),
    FailureCase(
        "mise",
        "mise install",
        _build(
            ["mise node@20.11.0 install"],
            _pad("mise tool{i}@1.0.{i} installed", 40),
            ["mise ERROR failed to install python@3.13.0: checksum mismatch"],
            ["mise done"],
        ),
        ("checksum mismatch",),
    ),
    FailureCase(
        "file_listing",
        "find /srv -name '*.conf'",
        _build(
            ["/srv/app/a.conf"],
            _pad("/srv/app/sub{i}/file{i}.conf", 40),
            ["find: '/srv/secret': Permission denied"],
            ["/srv/z.conf"],
        ),
        ("Permission denied",),
    ),
    FailureCase(
        "file_content",
        "cat /var/log/app.log",
        _build(
            ["2024-01-01 10:00:00 INFO starting"],
            _pad("2024-01-01 10:00:{i} INFO request handled", 40),
            ["2024-01-01 10:05:00 ERROR unhandled exception: NullPointerException in Worker"],
            ["2024-01-01 10:06:00 INFO stopped"],
        ),
        ("NullPointerException",),
    ),
    FailureCase(
        "generic",
        "some-unknown-tool --run",
        _build(
            ["starting unknown tool"],
            _pad("step {i} complete", 100),
            ["FATAL: unrecoverable state, aborting"],
            ["done"],
        ),
        ("FATAL: unrecoverable state",),
    ),
]
