from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(sys.platform == "win32", "Native frame checks require Windows")
class NativeWindowsFrameTests(unittest.TestCase):
    def test_real_windows_frame_at_normal_and_scaled_dpi(self):
        root = Path(__file__).resolve().parents[1]
        for scale in ("1", "1.5"):
            with self.subTest(scale=scale):
                env = dict(os.environ, QT_QPA_PLATFORM="windows", QT_SCALE_FACTOR=scale)
                result = subprocess.run([sys.executable, str(root / "tools/check_window_frame.py")],
                    cwd=root, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('"native_frame_removed": true', result.stdout)
