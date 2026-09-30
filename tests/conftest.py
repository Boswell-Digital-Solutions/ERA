"""Test session guard.

The CLI publishes an evaluation export to the DataForge Local inbox when that
inbox exists. Point the inbox at a path that does not exist, so a test that runs
the CLI can never write into a real home directory. Tests of publishing set their
own inbox.
"""

import os
import tempfile
from pathlib import Path

os.environ["DFL_ERA_DROP_DIR"] = str(Path(tempfile.gettempdir()) / "era-tests-no-such-inbox")
