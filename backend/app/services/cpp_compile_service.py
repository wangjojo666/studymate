from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


COMPILE_TIMEOUT_SECONDS = 8
RUN_TIMEOUT_SECONDS = 5


def compile_and_run_cpp(code: str, sample_input: str = "") -> dict:
    if not code.strip():
        return {
            "compile_result": _compile_payload(
                success=False,
                compiler_available=False,
                command="",
                stderr="未提供 C++ 代码，已跳过编译诊断。",
            ),
            "run_result": _run_payload(executed=False),
        }

    compiler = shutil.which("g++")
    if not compiler:
        return {
            "compile_result": _compile_payload(
                success=False,
                compiler_available=False,
                command="g++ main.cpp -std=c++17 -Wall -Wextra -O0 -o main",
                stderr="未检测到 g++，已跳过编译诊断。请安装 MinGW-w64、MSYS2 或系统 g++ 后重试。",
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
        try:
            compile_process = subprocess.run(
                command,
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT_SECONDS,
                check=False,
            )
            compile_result = _compile_payload(
                success=compile_process.returncode == 0,
                compiler_available=True,
                command=command_text,
                stderr=compile_process.stderr,
            )
        except subprocess.TimeoutExpired:
            return {
                "compile_result": _compile_payload(
                    success=False,
                    compiler_available=True,
                    command=command_text,
                    stderr=f"编译超过 {COMPILE_TIMEOUT_SECONDS} 秒，已终止。",
                    timeout=True,
                ),
                "run_result": _run_payload(executed=False),
            }

        if not compile_result["success"]:
            return {"compile_result": compile_result, "run_result": _run_payload(executed=False)}

        if sample_input.strip() == "":
            return {"compile_result": compile_result, "run_result": _run_payload(executed=False)}

        try:
            run_process = subprocess.run(
                [str(exe)],
                cwd=tmp_path,
                input=sample_input,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT_SECONDS,
                check=False,
            )
            run_result = _run_payload(
                executed=True,
                success=run_process.returncode == 0,
                stdout=run_process.stdout,
                stderr=run_process.stderr,
                timeout=False,
            )
        except subprocess.TimeoutExpired as exc:
            run_result = _run_payload(
                executed=True,
                success=False,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timeout=True,
            )
        return {"compile_result": compile_result, "run_result": run_result}


def _compile_payload(
    success: bool,
    compiler_available: bool,
    command: str,
    stderr: str,
    timeout: bool = False,
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
    }


def _run_payload(
    executed: bool,
    success: bool = False,
    stdout: str = "",
    stderr: str = "",
    timeout: bool = False,
) -> dict:
    return {
        "executed": executed,
        "success": success,
        "stdout": str(stdout or "").strip()[:8000],
        "stderr": str(stderr or "").strip()[:8000],
        "timeout": timeout,
    }


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
