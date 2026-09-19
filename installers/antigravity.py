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

"""Antigravity CLI specific installer logic for Token-Saver."""

import os

from installers import common

ANTIGRAVITY_FILES = [
    *common.SHARED_FILES,
    "antigravity/antigravity-plugin.json",
    "antigravity/hooks.json",
    "antigravity/hook_aftertool.py",
]


def _plugin_dir():
    """Return where we install the plugin files for Antigravity CLI.

    Returns:
        Platform-specific Antigravity CLI plugin directory.
    """
    if common.IS_WINDOWS:
        appdata = os.environ.get(
            "APPDATA", os.path.join(common.home(), "AppData", "Roaming")
        )
        return os.path.join(
            appdata, "gemini", "antigravity-cli", "plugins", "token-saver"
        )
    return os.path.join(
        common.home(), ".gemini", "antigravity-cli", "plugins", "token-saver"
    )


def install(use_symlink=False):
    """Install Token-Saver for Antigravity CLI.

    Args:
        use_symlink: Whether to link source files instead of copying them.
    """
    target_dir = _plugin_dir()
    print(f"\n--- Antigravity CLI ({target_dir}) ---")
    common.install_files(target_dir, ANTIGRAVITY_FILES, use_symlink)
    common.stamp_version(target_dir, ["antigravity/antigravity-plugin.json"])


def uninstall():
    """Uninstall Token-Saver from Antigravity CLI."""
    print("\n--- Antigravity CLI ---")
    common.uninstall_dir(_plugin_dir())
