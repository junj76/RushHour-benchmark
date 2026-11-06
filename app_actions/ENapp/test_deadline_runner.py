import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from deadline_runner import supervise
from flow_controls import Screen
from home_recovery import Backend, home_visible, matches, recover


ROOT = Path(__file__).resolve().parent
FAKE_RETURN = """
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--ready');p.add_argument('--result');p.add_argument('--fail',action='store_true')
a=p.parse_args();Path(a.ready).write_text(json.dumps({'ready':True}))
request=json.loads(sys.stdin.readline())
Path(a.result).write_text(json.dumps({'home_verified':not a.fail,'restarted':False}))
"""


class DeadlineTests(unittest.TestCase):
    def run_scenario(self, source, action_time=0.3, failed_home=False):
        recovery = [sys.executable, '-u', '-c', FAKE_RETURN]
        if failed_home:
            recovery += ['--fail']
        with contextlib.redirect_stdout(io.StringIO()):
            return supervise([sys.executable, '-u', '-c', source], 'reddit', action_time, 1,
                             ROOT, recovery_command=recovery, prepare_limit=3)

    def test_blocked_operation_is_killed_at_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'late_action'
            source = "import time;from pathlib import Path;time.sleep(10);Path(%r).touch()" % str(marker)
            result, code = self.run_scenario(source)
            self.assertEqual(code, 0)
            self.assertEqual(result['status'], 'DEADLINE_RETURNED')
            self.assertEqual(result['scenario_status'], 'INTERRUPTED_AT_DEADLINE')
            self.assertLess(abs(result['return_requested_elapsed_seconds'] - 0.3), 0.25)
            self.assertLess(result['elapsed_seconds'], 2)
            self.assertFalse(marker.exists())
            self.assertTrue(result['home_verified'])

    def test_recovery_failure_cannot_report_success(self):
        source = "import json;print(json.dumps({'app':'reddit','status':'PASS','steps':[]}))"
        result, code = self.run_scenario(source, failed_home=True)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'HOME_FAILED')
        self.assertFalse(result['home_verified'])
        self.assertNotIn('home_elapsed_seconds', result)

    def test_blocked_return_process_is_also_bounded(self):
        fake = FAKE_RETURN.replace("request=json.loads(sys.stdin.readline())", 
                                   "request=json.loads(sys.stdin.readline());import time;time.sleep(10)")
        with contextlib.redirect_stdout(io.StringIO()):
            result, code = supervise([sys.executable, '-c', 'import time;time.sleep(10)'],
                                     'reddit', 0.1, 0.2, ROOT,
                                     recovery_command=[sys.executable, '-u', '-c', fake], prepare_limit=3)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'HOME_FAILED')
        self.assertLess(result['elapsed_seconds'], 2)

    def test_failed_preparation_never_starts_scenario(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'scenario_started'
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    supervise([sys.executable,'-c',"from pathlib import Path;Path(%r).touch()" % str(marker)],
                              'reddit',0.1,0.2,ROOT,recovery_command=[sys.executable,'-c','raise SystemExit(1)'],
                              prepare_limit=0.2)
            self.assertFalse(marker.exists())

    def test_deadline_retains_atomic_scenario_progress(self):
        source = """
import json,os,time
from pathlib import Path
path=Path(os.environ['ENAPP_PROGRESS_PATH'])
temp=path.with_suffix('.tmp')
temp.write_text(json.dumps({'app':'reddit','partial':True,'status':'RUNNING','steps':[
    {'name':'browse_down_1','status':'PASS','elapsed_seconds':0.1},
    {'name':'browse_down_2','status':'RUNNING'}]}))
temp.replace(path)
time.sleep(10)
"""
        result, code = self.run_scenario(source)
        self.assertEqual(code,0)
        self.assertTrue(result['scenario_progress_recovered'])
        self.assertFalse(result['scenario_actions_completed'])
        self.assertEqual(result['steps'][0]['status'],'PASS')
        self.assertEqual(result['steps'][1]['status'],'INTERRUPTED_AT_DEADLINE')

    def test_failed_checkpoint_keeps_business_failure_after_return(self):
        source = """
import json,os,time
from pathlib import Path
Path(os.environ['ENAPP_PROGRESS_PATH']).write_text(json.dumps({
    'app':'reddit','partial':True,'status':'FAIL','steps':[{'name':'browse_down_1','status':'FAIL'}]}))
time.sleep(10)
"""
        result, code = self.run_scenario(source)
        self.assertEqual(code,1)
        self.assertEqual(result['status'],'FAIL')
        self.assertTrue(result['home_verified'])

    def test_business_failure_is_preserved_after_successful_return(self):
        source = "import json;print(json.dumps({'app':'reddit','status':'FAIL','steps':[],'error':'missing post'}))"
        result, code = self.run_scenario(source)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['home_verified'])
        self.assertEqual(result['error'], 'missing post')

    def test_missing_business_result_is_not_completion(self):
        result, code = self.run_scenario("raise RuntimeError('broken import')")
        self.assertEqual(result['scenario_status'], 'NO_RESULT')
        self.assertNotEqual(code, 0)

    def test_home_requires_controls_not_just_package(self):
        screen = Screen('<hierarchy><node package="com.reddit.frontpage" bounds="[0,0][100,100]"/></hierarchy>',
                        'com.reddit.frontpage')
        self.assertFalse(home_visible('reddit', screen, {}))

    def test_known_home_xmls(self):
        for app in ('reddit', 'youtube'):
            cfg = json.loads((ROOT / 'profiles' / (app + '.json')).read_text(encoding='utf-8-sig'))
            path = ROOT / 'ui_dumps' / (app + '_home.xml')
            screen = Screen(path.read_text(encoding='utf-8-sig'), cfg['package'])
            self.assertTrue(home_visible(app, screen, cfg), app)

    def test_selector_boolean_and_regex(self):
        node = {'selected':'true','text':'Home'}
        self.assertTrue(matches(node, {'selected':True, 'textMatches':'(?i)home'}))
        self.assertFalse(matches(node, {'selected':False}))

    def test_gmail_compose_button_or_background_list_is_not_home(self):
        def screen(ids, web=False):
            xml = '<hierarchy>' + ''.join('<node package="com.google.android.gm" resource-id="com.google.android.gm:id/%s" bounds="[0,0][100,100]"/>' % rid for rid in ids)
            if web:
                xml += '<node package="com.google.android.gm" class="android.webkit.WebView" bounds="[0,0][100,100]"/>'
            xml += '</hierarchy>'
            return Screen(xml, 'com.google.android.gm')
        self.assertFalse(home_visible('gmail', screen(['compose_button']), {}))
        self.assertFalse(home_visible('gmail', screen(['thread_list_view', 'subject_and_folder_view']), {}))
        self.assertFalse(home_visible('gmail', screen(['thread_list_view'], web=True), {}))
        self.assertTrue(home_visible('gmail', screen(['thread_list_view']), {}))

    def test_background_app_nodes_do_not_prove_home_or_allow_back(self):
        class BackgroundBackend:
            def __init__(self):
                self.now = 0
            def screen(self):
                xml = '<hierarchy>' + ''.join('<node package="pkg" resource-id="%s" bounds="[0,0][10,10]"/>' % rid
                                              for rid in ('main_top_app_bar_search','bottom_nav','feed_lazy_column')) + '</hierarchy>'
                result = Screen(xml, 'pkg')
                result.foreground_package = 'another.app'
                return result
            def back(self):
                raise AssertionError('Must not press Back in another application')
            def sleep(self, seconds):
                self.now += seconds
        backend = BackgroundBackend()
        result = recover(backend,'reddit',{},2,clock=lambda:backend.now,pause=backend.sleep)
        self.assertFalse(result['home_verified'])
        self.assertEqual(result['back_count'],0)

    def test_normal_back_before_restart_and_home_verification(self):
        class FakeBackend:
            def __init__(self):
                self.calls = []
                self.restarted = False
                self.now = 0

            def screen(self):
                ids = ['main_top_app_bar_search','bottom_nav','feed_lazy_column'] if self.restarted else ['post_detail']
                xml = '<hierarchy>' + ''.join('<node package="pkg" resource-id="%s" bounds="[0,0][10,10]"/>' % rid for rid in ids) + '</hierarchy>'
                return Screen(xml, 'pkg')

            def back(self): self.calls.append('back')
            def restart(self): self.calls.append('restart'); self.restarted = True
            def sleep(self, seconds): self.now += seconds

        backend = FakeBackend()
        result = recover(backend, 'reddit', {}, 8, clock=lambda: backend.now, pause=backend.sleep)
        self.assertEqual(backend.calls, ['back','back','back','restart'])
        self.assertTrue(result['home_verified'])
        self.assertTrue(result['restarted'])

    def test_zero_return_budget_issues_no_commands(self):
        class Backend:
            def screen(self): raise AssertionError('must not act')
        result = recover(Backend(), 'reddit', {}, 0)
        self.assertFalse(result['home_verified'])

    def test_restart_uses_resolved_explicit_activity(self):
        for package, activity in (
            ("com.google.android.googlequicksearchbox", ".SearchActivity"),
            ("com.tripadvisor.tripadvisor", "com.tripadvisor.android.ui.launcher.LauncherActivity"),
            ("com.booking", ".startup.HomeActivity"),
            ("com.google.android.gm", ".ConversationListActivityGmail"),
        ):
            with self.subTest(package=package):
                backend = object.__new__(Backend)
                backend.cfg = {"package": package}
                backend.adb = Mock()
                component = package + "/" + activity
                backend.adb.shell.side_effect = ["priority=0\n" + component + "\n", "", "Starting: Intent"]
                backend.restart()
                commands = [call.args[0] for call in backend.adb.shell.call_args_list]
                self.assertEqual(commands[0][:3], ["cmd", "package", "resolve-activity"])
                self.assertEqual(commands[1], ["am", "force-stop", package])
                self.assertEqual(commands[2], ["am", "start", "-a", "android.intent.action.MAIN", "-c",
                                                "android.intent.category.LAUNCHER", "-n", component])

    def test_restart_does_not_stop_app_when_resolution_fails(self):
        for response in ("No activity found", TimeoutError("adb read timeout")):
            with self.subTest(response=str(response)):
                backend = object.__new__(Backend)
                backend.cfg = {"package": "com.example"}
                backend.adb = Mock()
                backend.adb.shell.side_effect = [response]
                with self.assertRaises((RuntimeError, TimeoutError)):
                    backend.restart()
                self.assertEqual(backend.adb.shell.call_count, 1)

    def test_restart_reports_launch_error(self):
        backend = object.__new__(Backend)
        backend.cfg = {"package": "com.example"}
        backend.adb = Mock()
        backend.adb.shell.side_effect = ["com.example/.MainActivity", "", "Error: Activity not started"]
        with self.assertRaisesRegex(RuntimeError, "Activity not started"):
            backend.restart()

    def test_rpc_closes_http_connection_and_sets_tunnel_timeout(self):
        backend = object.__new__(Backend)
        backend.adb = Mock()
        backend.device = Mock(_device_server_port=9008)
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b'{"result":"xml"}'
        with patch('home_recovery.HTTPConnection', return_value=connection):
            self.assertEqual(backend.rpc('dumpWindowHierarchy', [False,50]), 'xml')
        backend.adb.create_connection.return_value.settimeout.assert_called_once_with(0.65)
        connection.close.assert_called_once()

    def test_rpc_failure_closes_connection(self):
        backend = object.__new__(Backend)
        backend.adb = Mock()
        backend.device = Mock(_device_server_port=9008)
        connection = Mock()
        connection.request.side_effect = TimeoutError('blocked')
        with patch('home_recovery.HTTPConnection', return_value=connection):
            with self.assertRaises(TimeoutError):
                backend.rpc('deviceInfo', [])
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
