from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

SAFE_MODE_MESSAGE = "当前处于安全演示模式，未执行本地编译运行。"
PRODUCTION_REJECT_MESSAGE = (
    "生产环境未配置真实 C++ 沙箱，已拒绝本地编译运行。当前能力只有临时目录和 timeout。"
)
UNSUPPORTED_SANDBOX_MESSAGE = "CPP_RUN_SANDBOX={sandbox} 尚未实现，未执行本地编译运行。"


def compile_and_run_cpp(code: str, sample_input: str = "") -> dict:
    sandbox_level = "local_tempdir_timeout_only" if settings.cpp_run_enabled else "disabled"
    if not settings.cpp_run_enabled:
        return {
            "sandbox_level": sandbox_level,
            "compile_result": _compile_payload(
                success=False,
                compiler_available=bool(shutil.which("g++")),
                command="",
                stderr=SAFE_MODE_MESSAGE,
                executed=False,
            ),
            "run_result": _run_payload(executed=False),
        }

    if settings.cpp_run_sandbox != "none":
        message = UNSUPPORTED_SANDBOX_MESSAGE.format(sandbox=settings.cpp_run_sandbox)
        return {
            "sandbox_level": f"unsupported:{settings.cpp_run_sandbox}",
            "compile_result": _compile_payload(
                success=False,
                compiler_available=bool(shutil.which("g++")),
                command="",
                stderr=message,
                executed=False,
            ),
            "run_result": _run_payload(executed=False),
        }

    if settings.app_env == "production":
        return {
            "sandbox_level": "rejected_no_sandbox",
            "compile_result": _compile_payload(
                success=False,
                compiler_available=bool(shutil.which("g++")),
                command="",
                stderr=PRODUCTION_REJECT_MESSAGE,
                executed=False,
            ),
            "run_result": _run_payload(executed=False),
        }

    if not code.strip():
        return {
            "sandbox_level": sandbox_level,
            "compile_result": _compile_payload(
                success=False,
                compiler_available=False,
                command="",
                stderr="未提供 C++ 代码，已跳过编译诊断。",
                executed=False,
            ),
            "run_result": _run_payload(executed=False),
        }

    compiler = shutil.which("g++")
    if not compiler:
        return {
            "sandbox_level": sandbox_level,
            "compile_result": _compile_payload(
                success=False,
                compiler_available=False,
                command="g++ main.cpp -std=c++17 -Wall -Wextra -O0 -o main",
                stderr="未检测到 g++，已跳过编译诊断。请安装 MinGW-w64、MSYS2 或系统 g++ 后重试。",
                executed=False,
            ),
            "run_result": _run_payload(executed=False),
        }

    with tempfile.TemporaryDirectory(prefix="studymate_cpp_") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "main.cpp"
        exe = tmp_path / ("main.exe" if _is_windows() else "main")
        source.write_text(code, encoding="utf-8")
        command = [compiler, "main.cpp", "-std=c++17", "-Wall", "-Wextra", "-O0", "-o", exe.name]
        command_text = "g++ main.cpp -std=c++17 -Wall -Wextra -O0 -o main"
        compile_process = _run_process_limited(
            command,
            cwd=tmp_path,
            timeout=settings.cpp_compile_timeout_seconds,
            output_limit=settings.cpp_output_limit_bytes,
        )
        compile_result = _compile_payload(
            success=compile_process.returncode == 0,
            compiler_available=True,
            command=command_text,
            stderr=compile_process.stderr,
            timeout=compile_process.timeout,
            output_limit_exceeded=compile_process.output_limit_exceeded,
        )

        if not compile_result["success"]:
            return {
                "sandbox_level": sandbox_level,
                "compile_result": compile_result,
                "run_result": _run_payload(executed=False),
            }

        if sample_input.strip() == "":
            return {
                "sandbox_level": sandbox_level,
                "compile_result": compile_result,
                "run_result": _run_payload(executed=False),
            }

        run_process = _run_process_limited(
            [str(exe)],
            cwd=tmp_path,
            input_text=sample_input,
            timeout=settings.cpp_run_timeout_seconds,
            output_limit=settings.cpp_output_limit_bytes,
        )
        run_result = _run_payload(
            executed=True,
            success=(
                run_process.returncode == 0
                and not run_process.timeout
                and not run_process.output_limit_exceeded
            ),
            stdout=run_process.stdout,
            stderr=run_process.stderr,
            timeout=run_process.timeout,
            output_limit_exceeded=run_process.output_limit_exceeded,
        )
        return {
            "sandbox_level": sandbox_level,
            "compile_result": compile_result,
            "run_result": run_result,
        }


def _compile_payload(
    success: bool,
    compiler_available: bool,
    command: str,
    stderr: str,
    timeout: bool = False,
    executed: bool = True,
    output_limit_exceeded: bool = False,
) -> dict:
    warnings, errors = _split_diagnostics(stderr)
    return {
        "success": success,
        "compiler": "g++",
        "compiler_available": compiler_available,
        "command": command,
        "stderr": stderr.strip()[:8000],
        "warnings": warnings,
        "errors": errors,
        "timeout": timeout,
        "output_limit_exceeded": output_limit_exceeded,
        "executed": executed,
    }


def _run_payload(
    executed: bool,
    success: bool = False,
    stdout: str = "",
    stderr: str = "",
    timeout: bool = False,
    output_limit_exceeded: bool = False,
) -> dict:
    return {
        "executed": executed,
        "success": success,
        "stdout": str(stdout or "").strip()[:8000],
        "stderr": str(stderr or "").strip()[:8000],
        "timeout": timeout,
        "output_limit_exceeded": output_limit_exceeded,
    }


@dataclass(frozen=True)
class _ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timeout: bool
    output_limit_exceeded: bool


def _run_process_limited(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    output_limit: int,
    input_text: str = "",
) -> _ProcessResult:
    """Run a process while bounding captured output before it reaches application memory."""
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(  # noqa: S603 - command is an explicit executable/argument list.
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    limit = max(1024, output_limit)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    output_limit_hit = threading.Event()

    def drain(name: str, pipe) -> None:
        while chunk := pipe.read(8192):
            remaining = limit - len(buffers[name])
            if remaining > 0:
                buffers[name].extend(chunk[:remaining])
            if len(chunk) > remaining:
                output_limit_hit.set()
                break

    readers = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()

    if process.stdin is not None:
        try:
            process.stdin.write(input_text.encode("utf-8"))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    deadline = time.monotonic() + max(1, timeout)
    timed_out = False
    while process.poll() is None:
        if output_limit_hit.is_set():
            _terminate_process_tree(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_process_tree(process)
            break
        time.sleep(0.01)

    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        process.wait(timeout=2)
    for reader in readers:
        reader.join(timeout=1)

    return _ProcessResult(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout=buffers["stdout"].decode("utf-8", errors="replace"),
        stderr=buffers["stderr"].decode("utf-8", errors="replace"),
        timeout=timed_out,
        output_limit_exceeded=output_limit_hit.is_set(),
    )


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(  # noqa: S603 - fixed system utility and numeric PID.
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _split_diagnostics(stderr: str) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    for line in stderr.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if re.search(r"\bwarning:", clean, flags=re.I):
            warnings.append(clean[:500])
        if re.search(r"\berror:|undefined reference|collect2:", clean, flags=re.I):
            errors.append(clean[:500])
    return warnings[:12], errors[:12]


def _is_windows() -> bool:
    return shutil.which("cmd") is not None
