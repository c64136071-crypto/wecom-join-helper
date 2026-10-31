"""Trusted owned-DOM resources. No existing browser/profile/window discovery."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from typing import Any

DOM_CAPABILITIES = {
    'owned-dom-form': frozenset({'name', 'quantity', 'save', 'receipt'}),
    'owned-dom-report': frozenset({'period', 'export', 'total', 'receipt'}),
}


def append_event(path, event):
    with Path(path).open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, sort_keys=True) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


class OwnedJob:
    """Private Win32 containment; signals a retained job handle, never arbitrary PIDs."""
    def __init__(self, ledger):
        if os.name != 'nt':
            raise OSError('owned_dom_windows_required')
        self.ledger = Path(ledger)
        self.handles = {}
        self.records = {}
        self.report = None
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        k = self.k
        k.CreateJobObjectW.argtypes, k.CreateJobObjectW.restype = [ctypes.c_void_p, w.LPCWSTR], w.HANDLE
        k.SetInformationJobObject.argtypes, k.SetInformationJobObject.restype = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL
        k.AssignProcessToJobObject.argtypes, k.AssignProcessToJobObject.restype = [w.HANDLE, w.HANDLE], w.BOOL
        k.QueryInformationJobObject.argtypes, k.QueryInformationJobObject.restype = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)], w.BOOL
        k.TerminateJobObject.argtypes, k.TerminateJobObject.restype = [w.HANDLE, w.UINT], w.BOOL
        k.OpenProcess.argtypes, k.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
        k.GetProcessTimes.argtypes, k.GetProcessTimes.restype = [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME)], w.BOOL
        k.WaitForSingleObject.argtypes, k.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
        k.CloseHandle.argtypes, k.CloseHandle.restype = [w.HANDLE], w.BOOL
        class BasicLimits(ctypes.Structure):
            _fields_ = [('processTime', ctypes.c_longlong), ('jobTime', ctypes.c_longlong),
                        ('flags', w.DWORD), ('minWS', ctypes.c_size_t), ('maxWS', ctypes.c_size_t),
                        ('activeLimit', w.DWORD), ('affinity', ctypes.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', BasicLimits), ('io', ctypes.c_ulonglong * 6),
                        ('processMemory', ctypes.c_size_t), ('jobMemory', ctypes.c_size_t),
                        ('peakProcess', ctypes.c_size_t), ('peakJob', ctypes.c_size_t)]
        self.handle = k.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            k.CloseHandle(self.handle)
            raise ctypes.WinError(ctypes.get_last_error())
        append_event(self.ledger, {'event': 'private_job_created', 'ownerPid': os.getpid()})

    def _retain(self, pid):
        if pid in self.records:
            return
        handle = self.k.OpenProcess(0x100000 | 0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error != 87:  # Process disappeared after a membership snapshot, not access denied.
                raise ctypes.WinError(error)
            record = {'event': 'owned_process_observed_exited', 'pid': pid,
                      'creationTime': None, 'lookupError': error, 'exitedBeforeRetain': True}
        else:
            creation, exit_time, kernel, user = (w.FILETIME() for _ in range(4))
            if not self.k.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)):
                self.k.CloseHandle(handle)
                raise ctypes.WinError(ctypes.get_last_error())
            self.handles[pid] = handle
            record = {'event': 'owned_process_retained', 'pid': pid,
                      'creationTime': creation.dwLowDateTime | creation.dwHighDateTime << 32}
        self.records[pid] = record
        append_event(self.ledger, record)

    def assign(self, process):
        append_event(self.ledger, {'event': 'owned_popen_created', 'pid': process.pid})
        # Node is not allowed to create any resources before its later file handshake.
        if not self.k.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._retain(process.pid)
        append_event(self.ledger, {'event': 'assigned_to_private_job', 'pid': process.pid})

    def snapshot(self):
        buffer = ctypes.create_string_buffer(65536)
        returned = w.DWORD()
        if not self.k.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), ctypes.byref(returned)):
            raise ctypes.WinError(ctypes.get_last_error())
        header = (w.DWORD * 2).from_buffer(buffer)
        count = int(header[1])
        if count > 4096:
            raise OSError('job_membership_overflow')
        pids = list((ctypes.c_size_t * count).from_buffer(buffer, 8))
        for pid in pids:
            self._retain(int(pid))
        return [int(pid) for pid in pids]

    def cleanup(self):
        if self.report is not None:
            return self.report
        errors, active, readback = [], None, []
        until = time.monotonic() + 5
        try:
            self.snapshot()
        except OSError as exc:
            errors.append({'stage': 'membership_before', 'error': type(exc).__name__})
        try:
            if not self.k.TerminateJobObject(self.handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
        except OSError as exc:
            errors.append({'stage': 'terminate_owned_job', 'error': type(exc).__name__})
        try:
            while True:
                active = self.snapshot()
                if not active or time.monotonic() >= until:
                    break
                time.sleep(0.02)
        except OSError as exc:
            errors.append({'stage': 'membership_after', 'error': type(exc).__name__})
        for pid, record in self.records.items():
            remaining_ms = max(0, int((until - time.monotonic()) * 1000))
            wait = self.k.WaitForSingleObject(self.handles[pid], remaining_ms) if pid in self.handles else None
            readback.append({'pid': pid, 'creationTime': record['creationTime'], 'waitResult': wait,
                             'exited': wait == 0 or record.get('exitedBeforeRetain', False)})
        self.report = {'verified': not errors and active == [] and all(row['exited'] for row in readback),
                       'activeMembers': active, 'processReadback': readback, 'errors': errors}
        try:
            append_event(self.ledger, {'event': 'job_cleanup_readback', **self.report})
        finally:
            for handle in self.handles.values():
                self.k.CloseHandle(handle)
            self.k.CloseHandle(self.handle)
        return self.report


def save_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())


def publish_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    save_json(temp, value)
    if path.exists():
        raise FileExistsError('owned_message_already_exists')
    os.replace(temp, path)


class OwnedDomSession:
    def __init__(self, app_id, artifacts, options=None):
        if app_id not in {'owned-dom-form', 'owned-dom-report'}:
            raise ValueError('invalid_dom_adapter')
        self.app_id = app_id
        self.artifacts = Path(artifacts)
        self.directory = self.artifacts.parent / 'owned-dom'
        self.temp_dir = self.directory / 'runtime-temp'
        self.instance_id = uuid.uuid4().hex
        self.options = dict(options or {})
        if set(self.options) - {'server_only', 'headless'} or any(type(v) is not bool for v in self.options.values()):
            raise ValueError('invalid_dom_options')
        self.process: Any = None
        self.job: Any = None
        self.info, self.ports = {}, []
        self.port_owners = {}
        self.sequence = 0
        self.cleanup_report = self.startup_listeners = None

    def child_environment(self):
        env = {key: os.environ[key] for key in ['PATH', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT',
                                               'SYSTEMDRIVE', 'PROGRAMFILES', 'PROGRAMFILES(X86)'] if key in os.environ}
        home = self.temp_dir / 'home'
        home.mkdir()
        env.update(TEMP=str(self.temp_dir), TMP=str(self.temp_dir), TMPDIR=str(self.temp_dir),
                   HOME=str(home), USERPROFILE=str(home), LOCALAPPDATA=str(home / 'AppData/Local'),
                   APPDATA=str(home / 'AppData/Roaming'), PYTHONDONTWRITEBYTECODE='1')
        # Windows folder resolution fails for nonexistent redirected AppData paths.
        for key in ('LOCALAPPDATA', 'APPDATA'):
            Path(env[key]).mkdir(parents=True)
        return env

    def refresh(self):
        if self.job is not None:
            self.job.snapshot()
        self.read_resource_receipts()

    def read_resource_receipts(self):
        path = self.directory / 'server-info.json'
        if path.is_file():
            info = json.loads(path.read_text(encoding='utf-8'))
            if info['instanceId'] != self.instance_id or info['appId'] != self.app_id or info['nodePid'] != self.process.pid:
                raise OSError('owned_metadata_mismatch')
            port = info['httpPort']
            if type(port) is not int or not 1 <= port <= 65535 or port in {9222, 18080, 13306, 18883, 18884}:
                raise OSError('owned_port_rejected')
            self.info.update(info)
            self.ports = [port]
            self.port_owners = {port: self.process.pid}
        browser_path = self.directory / 'browser-info.json'
        if browser_path.is_file():
            browser = json.loads(browser_path.read_text(encoding='utf-8'))
            if browser['browserPid'] not in self.job.records:
                raise OSError('browser_job_ownership_unverified')
            if not Path(browser['profilePath']).resolve().is_relative_to(self.temp_dir.resolve()):
                raise OSError('profile_ownership_rejected')
            port = browser['cdpPort']
            if type(port) is not int or not 1 <= port <= 65535 or port in {9222, 18080, 13306, 18883, 18884}:
                raise OSError('owned_port_rejected')
            self.info.update(browser)
            self.ports.append(port)
            self.port_owners[port] = browser['browserPid']

    def listener_readback(self, label):
        if not self.ports:
            return {'querySuccess': True, 'rows': [], 'verified': True, 'queriedPorts': []}
        ports = ','.join(str(port) for port in self.ports)
        script = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$ErrorActionPreference='Stop';"
            f"$ports=@({ports});$rows=@();foreach($port in $ports){{"
            "$issues=@();$items=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue -ErrorVariable issues);"
            "foreach($issue in $issues){if($issue.FullyQualifiedErrorId -notlike 'CmdletizationQuery_NotFound*'){throw 'scoped_listener_query_failed'}};"
            "$rows+=@($items|ForEach-Object{@{LocalAddress=[string]$_.LocalAddress;LocalPort=[int]$_.LocalPort;OwningProcess=[int]$_.OwningProcess;State=[string]$_.State}})};"
            "ConvertTo-Json -InputObject @($rows) -Compress"
        )
        out_path, err_path = self.directory / f'{label}-listeners.stdout.txt', self.directory / f'{label}-listeners.stderr.txt'
        with out_path.open('x', encoding='utf-8') as out, err_path.open('x', encoding='utf-8') as err:
            child = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                     stdout=out, stderr=err, stdin=subprocess.DEVNULL)
            append_event(self.directory / 'ownership.jsonl', {'event': 'owned_readback_process', 'pid': child.pid, 'label': label})
            try:
                exit_code = child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
                raise OSError('listener_readback_timeout') from None
        if exit_code != 0:
            raise OSError('listener_readback_failed')
        rows = json.loads(out_path.read_text(encoding='utf-8-sig'))
        if not isinstance(rows, list):
            raise OSError('listener_readback_invalid_shape')
        verified = rows == [] if label == 'cleanup' else (
            len(rows) == len(self.ports) and {r['LocalPort'] for r in rows} == set(self.ports) and
            all(r['LocalAddress'] == '127.0.0.1' and r['OwningProcess'] == self.port_owners[r['LocalPort']] for r in rows))
        return {'querySuccess': True, 'queriedPorts': list(self.ports), 'rows': rows, 'verified': verified}

    def start(self, checkpoint):
        self.directory.mkdir()
        self.temp_dir.mkdir()
        self.artifacts.mkdir(exist_ok=True)
        (self.directory / 'requests').mkdir()
        (self.directory / 'responses').mkdir()
        node = os.environ.get('OWNED_DOM_NODE', '')
        if not Path(node).is_file():
            raise OSError('owned_dom_dependency_missing')
        self.job = OwnedJob(self.directory / 'ownership.jsonl')
        env = self.child_environment()
        with (self.directory / 'node.stdout.txt').open('x') as out, (self.directory / 'node.stderr.txt').open('x') as err:
            self.process = subprocess.Popen([node, str(Path(__file__).with_name('workflow_dom_bridge.cjs')), str(self.directory)],
                                            env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            self.job.assign(self.process)
        except OSError:
            self.process.kill()
            self.process.wait(timeout=3)
            raise
        publish_json(self.directory / 'start.json', {'appId': self.app_id, 'instanceId': self.instance_id,
                                                   'serverOnly': self.options.get('server_only', False),
                                                   'headless': self.options.get('headless', False),
                                                   'playwrightPath': os.environ.get('OWNED_DOM_PLAYWRIGHT', ''),
                                                   'browserExe': os.environ.get('OWNED_DOM_BROWSER', ''),
                                                   'artifacts': str(self.artifacts)})
        while not (self.directory / 'ready.json').is_file():
            self.refresh()
            checkpoint()
            if self.process.poll() is not None or (self.directory / 'failure.json').exists():
                raise OSError('owned_dom_start_failed')
            time.sleep(0.01)
        self.refresh()
        self.startup_listeners = self.listener_readback('startup')
        if not self.startup_listeners['verified']:
            raise OSError('listener_ownership_unverified')
        checkpoint()

    def command(self, action, target, value, checkpoint=None):
        self.sequence += 1
        name = f'{self.sequence:06d}.json'
        until = time.monotonic() + 10
        publish_json(self.directory / 'requests' / name, {'action': action, 'target': target, 'value': value})
        response_path = self.directory / 'responses' / name
        while not response_path.is_file():
            self.refresh()
            if checkpoint is not None:
                checkpoint()
            if time.monotonic() >= until:
                raise TimeoutError('dom_command_timeout')
            time.sleep(0.01)
        response = json.loads(response_path.read_text(encoding='utf-8'))
        if not response['ok']:
            raise OSError(response['reason'])
        return response.get('value')

    def send_bytes(self, raw):
        if len(raw) > 65536:
            raise OSError('dom_message_too_large')
        message = json.loads(raw)
        if type(message) is not dict or set(message) != {'action', 'target', 'value'}:
            raise ValueError('invalid_dom_message')
        self.sequence += 1
        self.pending_response = self.directory / 'responses' / f'{self.sequence:06d}.json'
        publish_json(self.directory / 'requests' / self.pending_response.name, message)

    def poll(self, timeout):
        self.refresh()
        if not self.pending_response.is_file():
            time.sleep(min(timeout, 0.01))
        return self.pending_response.is_file()

    def recv_bytes(self, maximum):
        with self.pending_response.open('rb') as handle:
            raw = handle.read(maximum + 1)
        if len(raw) > maximum:
            raise OSError('dom_message_too_large')
        return raw

    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def close(self):
        if self.cleanup_report is not None:
            return self.cleanup_report
        errors, job, listeners = [], None, None
        try:
            self.refresh()
        except (OSError, ValueError):
            errors.append('ownership_refresh_failed')
        if self.process is not None:
            try:
                (self.directory / 'stop').touch(exist_ok=False)
                until = time.monotonic() + 2
                while self.process.poll() is None and time.monotonic() < until:
                    self.refresh()
                    time.sleep(0.01)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if self.job is not None:
            try:
                job = self.job.cleanup()
            except OSError:
                errors.append('job_cleanup_failed')
        try:
            if self.process is not None:
                self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            errors.append('owned_node_exit_unverified')
        # Startup can publish ports during graceful shutdown. Read the final owned
        # receipts only after the Job is drained; its retained membership records
        # still bind the browser PID without querying an already closed Job handle.
        try:
            self.read_resource_receipts()
        except (OSError, ValueError):
            errors.append('final_resource_receipt_readback_failed')
        try:
            listeners = self.listener_readback('cleanup')
        except (OSError, ValueError):
            errors.append('listener_cleanup_unverified')
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
        except OSError:
            errors.append('owned_profile_cleanup_failed')
        self.cleanup_report = {'verified': not errors and (job is None or job['verified']) and
                               listeners is not None and listeners['verified'] and not self.temp_dir.exists(),
                               'job': job, 'listeners': listeners, 'ownedTempGone': not self.temp_dir.exists(), 'errors': errors}
        save_json(self.directory / 'cleanup.json', self.cleanup_report)
        return self.cleanup_report
