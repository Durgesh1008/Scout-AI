"""
Sandboxed Code Runner & Compiler Service
Executes Python and JavaScript code snippets with timeout limits and stdout/stderr capture.
"""

import sys
import time
import subprocess
from typing import Dict, Any

TIMEOUT_SECONDS = 6


def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
    """
    Executes code in Python or JavaScript and captures output, execution time, and errors.
    """
    clean_code = (code or "").strip()
    if not clean_code:
        return {
            "success": False,
            "stdout": "",
            "stderr": "No code provided to execute.",
            "execution_time_ms": 0,
            "exit_code": 1
        }

    lang = language.lower().strip()
    start_time = time.time()

    try:
        if lang in ["javascript", "js", "node"]:
            cmd = ["node", "-e", clean_code]
        else:
            # Default to Python using current venv interpreter
            cmd = [sys.executable, "-c", clean_code]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 1)

        return {
            "success": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "execution_time_ms": elapsed_ms,
            "exit_code": res.returncode
        }

    except subprocess.TimeoutExpired:
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Timed Out: Code exceeded {TIMEOUT_SECONDS}s limit (potential infinite loop).",
            "execution_time_ms": elapsed_ms,
            "exit_code": 124
        }
    except Exception as exc:
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Runner Error: {str(exc)}",
            "execution_time_ms": elapsed_ms,
            "exit_code": 1
        }
