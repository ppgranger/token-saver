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

"""Package version and platform-specific runtime data locations."""

import os

__version__ = "3.0.0"


def data_dir() -> str:
    """Return the token-saver data directory (for DB, config, logs).

    Uses %APPDATA%/token-saver on Windows, ~/.token-saver on Unix.

    Returns:
        Platform-specific directory for configuration, logs, and savings data.
    """
    if os.name == "nt":
        appdata = os.environ.get(
            "APPDATA",
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming"),
        )
        return os.path.join(appdata, "token-saver")
    return os.path.join(os.path.expanduser("~"), ".token-saver")
