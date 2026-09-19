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

"""Example custom processor for ansible-playbook output.

Copy this file to ~/.token-saver/processors/ to activate it:

    cp examples/custom_processor/ansible_output.py ~/.token-saver/processors/

The processor will be auto-discovered on the next command execution.
"""

import re

import src.processors.base


class AnsibleOutputProcessor(src.processors.base.Processor):
    """Summarize successful Ansible tasks while retaining failure details."""

    priority = 35
    hook_patterns = [r"^ansible-playbook\s"]

    @property
    def name(self) -> str:
        """Return the processor name used for registration and statistics."""
        return "ansible"

    def can_handle(self, command: str) -> bool:
        """Return whether the command invokes ansible-playbook."""
        return bool(re.match(r"ansible-playbook\s", command.strip()))

    def process(self, command: str, output: str) -> str:
        """Summarize successful tasks and retain failure lines and headers."""
        lines = output.splitlines()
        result = []
        ok_count = 0
        changed_count = 0
        failed_tasks = []

        for line in lines:
            stripped = line.strip()

            # Always keep play/task headers
            if stripped.startswith(("PLAY [", "TASK [", "PLAY RECAP")):
                if ok_count or changed_count:
                    result.append(
                        f"  ... {ok_count} ok, "
                        f"{changed_count} changed (collapsed)"
                    )
                    ok_count = 0
                    changed_count = 0
                result.append(line)
                continue

            # Keep failed/fatal tasks
            if "fatal:" in stripped or "failed:" in stripped:
                result.append(line)
                failed_tasks.append(line)
                continue

            # Count ok/changed
            if stripped.startswith("ok:"):
                ok_count += 1
                continue
            if stripped.startswith("changed:"):
                changed_count += 1
                continue

            # Keep recap and everything else
            result.append(line)

        if ok_count or changed_count:
            result.append(
                f"  ... {ok_count} ok, {changed_count} changed (collapsed)"
            )

        return "\n".join(result)
