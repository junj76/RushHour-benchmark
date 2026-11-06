import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("batch", Path(__file__).with_name("batch_test_apps.py"))
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class BatchTests(unittest.TestCase):
    def test_result_parser_ignores_noise_and_nested_detail(self):
        value = {"app": "reddit", "status": "PASS", "steps": [
            {"name": "return_home", "detail": {"home_verified": True}}]}
        output = "log { not json\n" + json.dumps(value, indent=2) + "\nmore logs\n"
        self.assertEqual(batch.extract_result(output, "reddit"), value)
        self.assertIsNone(batch.extract_result(output[:-20], "other"))

    def test_return_timing_is_not_total_or_home_proof(self):
        result = {"app": "reddit", "status": "COMPLETED", "elapsed_seconds": 17,
                  "steps": [{"name": "browse_down_1", "status": "PASS", "elapsed_seconds": 6},
                            {"name": "return_home", "status": "PASS", "elapsed_seconds": 2,
                             "detail": {"home_verified": False}}]}
        row = batch.summarize("reddit", result, 18, 0, False, "log")
        self.assertEqual(row["return_steps_seconds"], 2)
        self.assertEqual(row["script_wall_seconds"], 18)
        self.assertFalse(row["reported_home_verified"])
        self.assertIsNone(row["reported_home_elapsed_seconds"])
        self.assertEqual(row["slowest_step"], "browse_down_1")

    def test_timeout_and_nonreturning_flow_do_not_invent_metrics(self):
        row = batch.summarize("youtube_shorts", None, 0.2, -9, True, "log")
        self.assertEqual(row["status"], "TIMEOUT")
        self.assertIsNone(row["return_steps_seconds"])
        self.assertIsNone(row["reported_home_verified"])
        self.assertEqual(row["return_steps_status"], "NO_RECORDED_STEPS")

    def test_real_child_timeout_and_partial_log(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "child.log"
            code, wall, expired = batch.run_logged(
                [sys.executable, "-u", "-c", "import time; print('started', flush=True); time.sleep(10)"],
                log, 0.5, temp, None)
            self.assertTrue(expired)
            self.assertNotEqual(code, 0)
            self.assertLess(wall, 5)
            self.assertIn("started", log.read_text())

    def test_full_batch_reports_continue_after_failure_without_phone(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "profiles").mkdir()
            (folder / "run_app.py").write_text(
                "APP_SCRIPTS = {'first': 'first.py', 'second': 'second.py', 'youtube_shorts': 'shorts.py'}")
            for app in ("first", "second"):
                (folder / "profiles" / (app + ".json")).write_text(json.dumps({"package": "com." + app}))
                result = {"app": app, "status": "PASS" if app == "first" else "FAIL", "steps": [
                    {"name": "return_home", "status": "PASS" if app == "first" else "FAIL",
                     "elapsed_seconds": 1, "detail": {"home_verified": app == "first"}}]}
                (folder / (app + ".py")).write_text(
                    "import json\nprint(json.dumps(" + repr(result) + "))\n")

            def fake_run(command, **kwargs):
                if command[-1] == "devices":
                    stdout = "List of devices attached\nserial device\n"
                elif command[-3:] == ["pm", "list", "packages"]:
                    stdout = "package:com.first\npackage:com.second\n"
                elif "resolve-activity" in command:
                    stdout = command[-1] + "/.Main\n"
                else:
                    raise AssertionError(command)
                return batch.subprocess.CompletedProcess(command, 0, stdout=stdout)

            original_run_logged = batch.run_logged

            def fake_launch(command, log, limit, cwd, env):
                if "am" in command:
                    log.write_text("Status: ok\n")
                    return 0, 0.01, False
                return original_run_logged(command, log, limit, cwd, env)

            with patch.object(sys, "argv", ["batch", "--dir", temp, "--settle", "0", "--diagnostic"]), \
                    patch.object(batch.shutil, "which", return_value=sys.executable), \
                    patch.object(batch.subprocess, "run", side_effect=fake_run), \
                    patch.object(batch, "run_logged", side_effect=fake_launch), \
                    patch.dict(batch.os.environ, {"ANDROID_SERIAL": "serial"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(batch.main(), 0)
            output = next((folder / "timing_results").iterdir())
            with (output / "summary.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual({row["app"] for row in rows}, {"first", "second"})
            self.assertEqual({row["status"] for row in rows}, {"PASS", "FAIL"})
            self.assertTrue((output / "report.html").is_file())
            self.assertTrue((output / "steps.csv").is_file())
            self.assertEqual(len(json.loads((output / "results.json").read_text(encoding="utf-8"))["results"]), 2)

    def test_guarded_batch_uses_supervisor_and_stops_on_failed_home(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "profiles").mkdir()
            (folder / "run_app.py").write_text("APP_SCRIPTS = {'first':'first.py','second':'second.py'}")
            for app in ('first','second'):
                (folder / 'profiles' / (app + '.json')).write_text(json.dumps({'package':'com.' + app}))
            launched = []

            def fake_run(command, **kwargs):
                if command[-1] == 'devices':
                    text = 'List of devices attached\nserial device\n'
                elif command[-3:] == ['pm','list','packages']:
                    text = 'package:com.first\npackage:com.second\n'
                else:
                    text = command[-1] + '/.Shell$HomeActivity\n'
                return batch.subprocess.CompletedProcess(command, 0, stdout=text)

            def fake_logged(command, log, limit, cwd, env):
                if 'am' in command:
                    self.assertIn('-p', command)
                    self.assertNotIn('-n', command)
                    log.write_text('Status: ok\n')
                    return 0, 0.01, False
                self.assertEqual(Path(command[2]).name, 'run_app.py')
                app = command[command.index('--app') + 1]
                launched.append(app)
                log.write_text(json.dumps({'app':app,'status':'HOME_FAILED','home_verified':False,'steps':[]}))
                return 1, 0.1, False

            with patch.object(sys, 'argv', ['batch','--dir',temp,'--settle','0']), \
                    patch.object(batch.shutil, 'which', return_value=sys.executable), \
                    patch.object(batch.subprocess, 'run', side_effect=fake_run), \
                    patch.object(batch, 'run_logged', side_effect=fake_logged), \
                    patch.dict(batch.os.environ, {'ANDROID_SERIAL':'serial'}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(batch.main(), 1)
            self.assertEqual(launched, ['first'])


if __name__ == "__main__":
    unittest.main()
