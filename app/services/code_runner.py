"""
Sandboxed Code Runner & Compiler Service
Executes Python and JavaScript code snippets with pre-execution AST safety inspection,
isolated environment variables, ephemeral scratch directories, and strict execution ceilings.

SECURITY NOTICE:
This runner enforces AST inspection and standard library restrictions suitable for
student algorithmic challenges. For untrusted public multi-tenant environments,
integrate containerized microVM isolation (e.g. Docker, gVisor, or Firecracker).
"""

import ast
import os
import sys
import time
import shutil
import tempfile
import subprocess
from typing import Dict, Any

TIMEOUT_SECONDS = 3.0
MAX_OUTPUT_BYTES = 10000

# Prohibited Python modules and calls that could interact with host/system
DISALLOWED_PYTHON_MODULES = {
    "os", "subprocess", "sys", "shutil", "socket", "http", "urllib",
    "requests", "ctypes", "pty", "commands", "builtins", "__builtin__",
    "posix", "nt", "importlib", "pickle", "shelve", "multiprocessing",
    "threading", "signal", "tempfile", "pathlib", "glob"
}

DISALLOWED_PYTHON_BUILTINS = {
    "eval", "exec", "compile", "open", "__import__", "globals", "locals"
}

# Prohibited JavaScript tokens
DISALLOWED_JS_PATTERNS = [
    "require('fs')", 'require("fs")', "require('child_process')", 'require("child_process")',
    "require('net')", 'require("net")', "require('http')", 'require("http")',
    "process.exit", "process.kill", "process.env", "child_process", "Function("
]


class SecurityASTValidator(ast.NodeVisitor):
    """Inspects Python AST to ensure code contains no host/OS access attempts."""
    def __init__(self):
        self.errors = []

    def visit_Import(self, node):
        for alias in node.names:
            base_module = alias.name.split(".")[0].lower()
            if base_module in DISALLOWED_PYTHON_MODULES:
                self.errors.append(f"Import of restricted module '{alias.name}' is prohibited in the sandbox.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            base_module = node.module.split(".")[0].lower()
            if base_module in DISALLOWED_PYTHON_MODULES:
                self.errors.append(f"Import from restricted module '{node.module}' is prohibited in the sandbox.")
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check direct calls to eval, exec, __import__, open
        if isinstance(node.func, ast.Name):
            if node.func.id in DISALLOWED_PYTHON_BUILTINS:
                self.errors.append(f"Call to restricted built-in function '{node.func.id}()' is prohibited.")
        self.generic_visit(node)


def validate_python_code(code: str) -> Dict[str, Any]:
    """Parse and validate Python AST before execution."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"valid": False, "error": f"SyntaxError on line {e.lineno}: {e.msg}"}

    validator = SecurityASTValidator()
    validator.visit(tree)

    if validator.errors:
        return {"valid": False, "error": "\n".join(validator.errors)}

    return {"valid": True, "error": None}


def validate_javascript_code(code: str) -> Dict[str, Any]:
    """Check JavaScript snippet for forbidden Node.js standard modules."""
    lower = code.lower()
    for pattern in DISALLOWED_JS_PATTERNS:
        if pattern.lower() in lower:
            return {
                "valid": False,
                "error": f"Security Error: Usage of restricted system API pattern '{pattern}' is prohibited."
            }
    return {"valid": True, "error": None}


def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
    """
    Executes Python or JavaScript code with pre-execution validation,
    isolated environment variables, ephemeral scratch directory, and timeout ceiling.
    """
    clean_code = (code or "").strip()
    if not clean_code:
        return {
            "success": False,
            "stdout": "",
            "stderr": "No code provided to execute.",
            "execution_time_ms": 0.0,
            "exit_code": 1
        }

    lang = language.lower().strip()

    # 1. Pre-execution static security verification
    if lang in ["javascript", "js", "node"]:
        validation = validate_javascript_code(clean_code)
    else:
        validation = validate_python_code(clean_code)

    if not validation["valid"]:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"🛡️ Sandbox Security Violation:\n{validation['error']}",
            "execution_time_ms": 0.0,
            "exit_code": 126
        }

    # 2. Ephemeral isolated scratch directory
    temp_dir = tempfile.mkdtemp(prefix="scout_sandbox_")

    # 3. Clean environment (Zero leakage of application secrets or host settings)
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
        "WINDIR": os.environ.get("WINDIR", "C:\\Windows"),
        "LANG": "en_US.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "NODE_ENV": "production"
    }

    start_time = time.time()

    try:
        if lang in ["javascript", "js", "node"]:
            cmd = ["node", "-e", clean_code]
        else:
            # -I: Isolated mode (ignores PYTHONPATH, user site-packages, and script dir)
            cmd = [sys.executable, "-I", "-c", clean_code]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=temp_dir,
            env=clean_env
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 1)

        stdout = res.stdout[:MAX_OUTPUT_BYTES]
        stderr = res.stderr[:MAX_OUTPUT_BYTES]

        if len(res.stdout) > MAX_OUTPUT_BYTES:
            stdout += "\n... [Output truncated: buffer limit exceeded]"
        if len(res.stderr) > MAX_OUTPUT_BYTES:
            stderr += "\n... [Output truncated: buffer limit exceeded]"

        return {
            "success": res.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "execution_time_ms": elapsed_ms,
            "exit_code": res.returncode
        }

    except subprocess.TimeoutExpired:
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"⏳ Execution Timeout: Solution exceeded the {TIMEOUT_SECONDS}s CPU limit. Check for infinite loops or non-terminating recursion.",
            "execution_time_ms": elapsed_ms,
            "exit_code": 124
        }
    except Exception as e:
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution Error: {str(e)}",
            "execution_time_ms": elapsed_ms,
            "exit_code": 1
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
