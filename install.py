#!/usr/bin/env python3
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

"""Installer / Uninstaller for Token-Saver extension.

Cross-platform: macOS, Linux, Windows.

Usage:
    python3 install.py --target claude        # Install for Claude Code
    python3 install.py --target antigravity   # Install for Antigravity CLI
    python3 install.py --target both          # Install for both
    python3 install.py --link                 # Use symlinks (development mode)
    python3 install.py --uninstall            # Remove from both platforms
    python3 install.py --uninstall --target claude  # Remove from Claude Code
"""

import argparse
import platform

import installers.common
from installers import antigravity
from installers import claude


def main():
    """Parse installation options and apply the requested platform action."""
    parser = argparse.ArgumentParser(
        description="Install or uninstall Token-Saver extension",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 install.py --target claude          Install for Claude Code
  python3 install.py --target antigravity     Install for Antigravity CLI
  python3 install.py --target both            Install for both
  python3 install.py --link --target claude   Dev mode (symlinks)
  python3 install.py --uninstall              Uninstall from both (default)
  python3 install.py --uninstall --target claude  Uninstall from Claude only
  python3 install.py --uninstall --keep-data  Uninstall but keep stats DB
""",
    )
    parser.add_argument(
        "--target",
        choices=["claude", "antigravity", "both"],
        default=None,
        help=(
            "Target platform (default: claude for install, both for uninstall)"
        ),
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Use symlinks instead of copies (development mode)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the extension completely",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help=(
            "When uninstalling, keep the ~/.token-saver data "
            "directory (stats, config)"
        ),
    )
    args = parser.parse_args()

    if args.uninstall:
        # Default to 'both' for uninstall so nothing is left behind
        target = args.target or "both"
        print(f"Uninstalling token-saver from: {target}")

        print("\n--- Legacy cleanup ---")
        installers.common.migrate_from_legacy()

        print("\n--- CLI ---")
        installers.common.uninstall_cli()

        if target in ("claude", "both"):
            claude.uninstall()
        if target in ("antigravity", "both"):
            antigravity.uninstall()

        print("\n--- Core ---")
        installers.common.uninstall_core()

        if not args.keep_data:
            print("\n--- Data ---")
            installers.common.uninstall_data_dir()

        print("\nUninstallation complete.")
        return

    # --- Install ---
    target = args.target or "claude"
    print(f"Installing token-saver for: {target}")
    print(f"Platform: {platform.system()}")
    print(f"Mode: {'symlink' if args.link else 'copy'}")

    # Clean up any leftover "token-saving" installation before proceeding
    print("\n--- Legacy cleanup ---")
    installers.common.migrate_from_legacy()

    if target in ("claude", "both"):
        claude.install(use_symlink=args.link)
    if target in ("antigravity", "both"):
        antigravity.install(use_symlink=args.link)

    installers.common.install_core(use_symlink=args.link)

    print("\n--- CLI ---")
    installers.common.install_cli(use_symlink=args.link)

    print("\nInstallation complete.")


if __name__ == "__main__":
    main()
