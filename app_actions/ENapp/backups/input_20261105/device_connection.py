"""Share one uiautomator2 service owner across independent ENapp processes."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import warnings

import adbutils
import uiautomator2 as u2


START_TIMEOUT = 40
IDLE_SECONDS = 1800


def _state_dir(serial):
    identity = "|".join((serial, sys.executable, importlib.metadata.version("uiautomator2"),
                         os.environ.get("ADB_SERVER_SOCKET", ""),
                         os.environ.get("ANDROID_ADB_SERVER_HOST", ""),
                         os.environ.get("ANDROID_ADB_SERVER_PORT", "")))
    folder = Path(tempfile.gettempdir()) / "rushhour-enapp-u2" / hashlib.sha256(identity.encode()).hexdigest()[:20]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _read_state(folder):
    try:
        return json.loads((folder / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(folder, value):
    temp = folder / ("state-%s.tmp" % os.getpid())
    temp.write_text(json.dumps(value), encoding="utf-8")
    os.replace(temp, folder / "state.json")


@contextmanager
def _startup_lock(folder):
    with (folder / "startup.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + START_TIMEOUT + 5
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for the ENapp service startup lock")
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _spawn_worker(serial, folder, token):
    command = [sys.executable, "-u", str(Path(__file__).resolve()),
               "--worker", serial, "--state-dir", str(folder), "--token", token]
    options = {"stdin": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = startup
    else:
        options["start_new_session"] = True
    with (folder / "worker.log").open("a", encoding="utf-8") as log:
        options.update(stdout=log, stderr=subprocess.STDOUT)
        return subprocess.Popen(command, **options)


def _pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stop_worker(folder):
    state = _read_state(folder)
    token = state.get("token")
    if not token or state.get("status") != "ready":
        return False
    if not _pid_alive(state.get("pid")):
        return False
    (folder / ("stop-" + token)).touch()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        current = _read_state(folder)
        if current.get("token") == token and current.get("status") in {"stopped", "error"}:
            return True
        time.sleep(0.05)
    raise RuntimeError("Service owner did not stop; see " + str(folder / "worker.log"))


class ReusedDevice(u2.Device):
    def start_uiautomator(self):
        folder = _state_dir(self._dev.serial)
        self._enapp_state = folder
        with self._lock, _startup_lock(folder):
            (folder / "last_used").touch()
            if self._check_alive():
                self.connection_mode = "reuse_running_server"
                return
            _stop_worker(folder)
            token = secrets.token_hex(12)
            _write_state(folder, {"token": token, "status": "starting"})
            process = _spawn_worker(self._dev.serial, folder, token)
            deadline = time.monotonic() + START_TIMEOUT
            while time.monotonic() < deadline:
                state = _read_state(folder)
                if state.get("token") == token:
                    if state.get("status") == "error":
                        raise RuntimeError("Service owner failed: " + state.get("error", "unknown"))
                    if state.get("status") == "ready" and self._check_alive():
                        self.connection_mode = "started_service_owner"
                        return
                if process.poll() is not None:
                    raise RuntimeError("Service owner exited; see " + str(folder / "worker.log"))
                time.sleep(0.05)
            (folder / ("stop-" + token)).touch()
            raise RuntimeError("Service owner startup timed out; see " + str(folder / "worker.log"))

    def stop_uiautomator(self, wait=True):
        # The library calls stop(wait=False) at client interpreter exit.
        if not wait:
            return
        folder = getattr(self, "_enapp_state", _state_dir(self._dev.serial))
        with self._lock, _startup_lock(folder):
            if _stop_worker(folder):
                return
            if self._check_alive():
                raise RuntimeError("Server belongs to another client; refusing to stop it")


def _supported():
    try:
        from uiautomator2.core import BasicUiautomatorServer
        return "wait" in inspect.signature(BasicUiautomatorServer.stop_uiautomator).parameters and all(
            hasattr(BasicUiautomatorServer, name) for name in
            ("_check_alive", "start_uiautomator", "stop_uiautomator"))
    except (ImportError, AttributeError, ValueError, TypeError):
        return False


def connect_device(serial=None):
    started = time.monotonic()
    serial = serial or os.environ.get("ANDROID_SERIAL")
    if os.environ.get("ENAPP_STANDARD_CONNECT") == "1" or not _supported():
        if os.environ.get("ENAPP_STANDARD_CONNECT") != "1":
            warnings.warn("Unsupported uiautomator2 internals; using standard connect", RuntimeWarning)
        device = u2.connect(serial)
        mode = "standard_connect"
    else:
        adb_device = serial if isinstance(serial, adbutils.AdbDevice) else adbutils.adb.device(serial=serial)
        device = ReusedDevice(adb_device)
        mode = device.connection_mode
    device.enapp_connection = {"mode": mode, "seconds": round(time.monotonic() - started, 4)}
    print("[device] %s connect=%.4fs" % (mode, device.enapp_connection["seconds"]), flush=True)
    return device


def _worker(serial, folder, token):
    device = None
    state = {"token": token, "pid": os.getpid(), "status": "starting", "serial": serial}
    try:
        device = u2.connect(serial)
        state["status"] = "ready"
        _write_state(folder, state)
        stop = folder / ("stop-" + token)
        while not stop.exists():
            process = getattr(device, "_process", None)
            if process is not None and process.pool() is not None:
                break
            try:
                if time.time() - (folder / "last_used").stat().st_mtime > IDLE_SECONDS:
                    break
            except FileNotFoundError:
                break
            time.sleep(0.2)
        state["status"] = "stopped"
    except Exception as exc:
        state.update(status="error", error="%s: %s" % (type(exc).__name__, exc))
    finally:
        try:
            if device is not None:
                device.stop_uiautomator(wait=True)
        finally:
            _write_state(folder, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--token", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        _worker(args.worker, args.state_dir, args.token)
        return 0
    if args.stop:
        adb_device = adbutils.adb.device(serial=args.serial or os.environ.get("ANDROID_SERIAL"))
        folder = _state_dir(adb_device.serial)
        with _startup_lock(folder):
            stopped = _stop_worker(folder)
        print("ENapp service owner stopped" if stopped else "No managed service owner")
        return 0
    device = connect_device(args.serial)
    started = time.monotonic()
    info = device.jsonrpc.deviceInfo(http_timeout=5)
    print(json.dumps({"uiautomator2": importlib.metadata.version("uiautomator2"),
                      "connection": device.enapp_connection,
                      "device_info_seconds": round(time.monotonic() - started, 4),
                      "rpc_verified": isinstance(info, dict)}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
