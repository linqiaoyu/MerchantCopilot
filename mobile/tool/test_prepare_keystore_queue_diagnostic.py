"""Generator safety checks; actual before/after heartbeat needs an Android run."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prepare_keystore_queue_diagnostic import generate


SOURCE = Path(__file__).resolve().parents[1] / "android/app/src/main/kotlin/com/merchantcopilot/v2/MainActivity.kt"
GENERATOR = Path(__file__).with_name("prepare_keystore_queue_diagnostic.py")


class KeystoreDiagnosticGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text()

    def test_diagnostic_records_source_and_bounded_delay_without_changing_storage(self):
        for delay in (1200, 6000):
            with self.subTest(delay=delay):
                result = generate(self.source, delay_ms=delay, variant="after")
                self.assertIn(hashlib.sha256(self.source.encode()).hexdigest(), result)
                self.assertIn(f"Thread.sleep({delay}L)", result)
                self.assertIn('"absolute_wall_limit_ms" to 120000', result)
                self.assertIn("maxOf(probeMaxGap, probeNow - probeLastBeat)", result)
                self.assertIn("} finally {", result)
                self.assertEqual(self.source.split("    private fun preferences()", 1)[1], result.split("    private fun preferences()", 1)[1])

    def test_no_diagnostic_entry_or_delay_in_ordinary_activity(self):
        self.assertNotIn("token_store_diagnostic", self.source)
        self.assertNotIn("Thread.sleep", self.source)

    def test_rejects_changed_or_already_instrumented_source(self):
        with self.assertRaises(ValueError):
            generate(self.source.replace("super.configureFlutterEngine(flutterEngine)", "super.configureFlutterEngine(other)"), delay_ms=1200, variant="before")
        with self.assertRaises(ValueError):
            generate(generate(self.source, delay_ms=1200, variant="after"), delay_ms=1200, variant="after")

    def test_rejects_invalid_delay_and_variant(self):
        for delay, variant in ((0, "after"), (10001, "before"), (1200, "unknown")):
            with self.subTest(delay=delay, variant=variant), self.assertRaises(ValueError):
                generate(self.source, delay_ms=delay, variant=variant)

    def test_cli_refuses_source_overwrite_and_existing_output(self):
        with tempfile.TemporaryDirectory(prefix="keystore-generator-test-") as temporary:
            source = Path(temporary) / "MainActivity.kt"
            source.write_text(self.source)
            output = Path(temporary) / "diagnostic.kt"
            output.write_text("preserve existing output")
            for target in (source, output):
                result = subprocess.run([sys.executable, str(GENERATOR), "--source", str(source), "--output", str(target), "--variant", "after"], capture_output=True, check=False)
                self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_text(), self.source)
            self.assertEqual(output.read_text(), "preserve existing output")


if __name__ == "__main__":
    unittest.main()
