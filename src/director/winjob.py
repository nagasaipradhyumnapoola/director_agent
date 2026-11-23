"""Best-effort Windows job object: kill-on-close plus memory/CPU limits."""

from __future__ import annotations

import ctypes
import os
from typing import Any


class WindowsJob:
    JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    def __init__(self, memory_mb: int, cpu_seconds: int):
        self.handle: Any = None
        self.applied = False
        self.error: str | None = None
        self._kernel32: Any = None
        self._wt: Any = None
        if os.name != "nt":
            self.error = "not-windows"
            return
        try:
            import ctypes.wintypes as wt

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class BASIC_LIMITS(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wt.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wt.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wt.DWORD),
                    ("SchedulingClass", wt.DWORD),
                ]

            class EXTENDED_LIMITS(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BASIC_LIMITS),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wt.HANDLE
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
            self.handle = handle
            info = EXTENDED_LIMITS()
            flags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | self.JOB_OBJECT_LIMIT_PROCESS_MEMORY
            if cpu_seconds > 0:
                flags |= self.JOB_OBJECT_LIMIT_PROCESS_TIME
            info.BasicLimitInformation.LimitFlags = flags
            info.ProcessMemoryLimit = max(64, memory_mb) * 1024 * 1024
            if cpu_seconds > 0:
                info.BasicLimitInformation.PerProcessUserTimeLimit = int(cpu_seconds * 10_000_000)
            if not kernel32.SetInformationJobObject(
                handle,
                self.JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
            self._kernel32 = kernel32
            self._wt = wt
        except Exception as exc:  # pragma: no cover - platform dependent
            self.error = type(exc).__name__
            self.close()

    def assign(self, process: Any) -> None:
        if not self.handle or os.name != "nt":
            return
        try:
            handle = self._wt.HANDLE(int(process._handle))
            ok = self._kernel32.AssignProcessToJobObject(self.handle, handle)
            self.applied = bool(ok)
            if not ok:
                self.error = "AssignProcessToJobObject failed"
        except Exception as exc:  # pragma: no cover
            self.error = type(exc).__name__

    def close(self) -> None:
        if self.handle and os.name == "nt":
            try:
                self._kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
