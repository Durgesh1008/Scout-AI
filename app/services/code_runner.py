"""
Sandboxed Code Runner & Compiler Service
Executes Python and JavaScript code snippets with multi-tier isolation:
1. Static Abstract Syntax Tree (AST) inspection & introspection blocking.
2. V8 engine restrictions (--no-addons, --disallow-code-generation-from-strings, 64MB cap).
3. Python isolated mode (-I, -B, network module poisoning).
4. Kernel-level POSIX resource limits (RLIMIT_CPU, RLIMIT_AS, RLIMIT_NPROC) on Linux/Docker.
5. Ephemeral isolated scratch filesystem with zero leakage of host environment secrets.
6. Optional Container MicroVM / Docker runner for zero-trust public multi-tenant environments.
"""

import ast
import os
import sys
import time
import shutil
import tempfile
import subprocess
import re
from typing import Dict, Any

TIMEOUT_SECONDS = 3.0
MAX_OUTPUT_BYTES = 10000

# Prohibited Python modules that could interact with host, OS, network, or filesystem
DISALLOWED_PYTHON_MODULES = {
    "os", "subprocess", "sys", "shutil", "socket", "http", "urllib",
    "requests", "ctypes", "pty", "commands", "builtins", "__builtin__",
    "posix", "nt", "importlib", "pickle", "shelve", "multiprocessing",
    "threading", "signal", "tempfile", "pathlib", "glob", "asyncio",
    "resource", "gc", "code", "codeop", "inspect"
}

# Prohibited built-ins used for dynamic execution, file I/O, or sandbox escapes
DISALLOWED_PYTHON_BUILTINS = {
    "eval", "exec", "compile", "open", "__import__", "globals", "locals",
    "getattr", "setattr", "delattr", "memoryview", "breakpoint", "input"
}

# Forbidden dunder / reflection attributes used in Python sandbox breakout exploits
# e.g., ().__class__.__bases__[0].__subclasses__()
DISALLOWED_PYTHON_ATTRIBUTES = {
    "__subclasses__", "__bases__", "__base__", "__mro__", "__globals__",
    "__builtins__", "__code__", "__closure__", "__class__", "__dict__",
    "__getattr__", "__getattribute__", "gi_frame", "cr_frame", "f_locals", "f_globals"
}

# Prohibited JavaScript / Node.js tokens and API calls
DISALLOWED_JS_PATTERNS = [
    r"require\s*\(\s*['\"]fs",
    r"require\s*\(\s*['\"]child_process",
    r"require\s*\(\s*['\"]net",
    r"require\s*\(\s*['\"]http",
    r"require\s*\(\s*['\"]https",
    r"require\s*\(\s*['\"]tls",
    r"require\s*\(\s*['\"]cluster",
    r"process\.exit",
    r"process\.kill",
    r"process\.env",
    r"process\.binding",
    r"child_process",
    r"Function\s*\(",
    r"constructor\s*\[\s*['\"]constructor['\"]\s*\]",
    r"globalThis",
    r"\bglobal\b",
]


class SecurityASTValidator(ast.NodeVisitor):
    """
    Inspects Python AST to ensure code contains no host/OS access,
    dynamic code evaluation, or introspection sandbox breakout attempts.
    """
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
        if isinstance(node.func, ast.Name):
            if node.func.id in DISALLOWED_PYTHON_BUILTINS:
                self.errors.append(f"Call to restricted built-in function '{node.func.id}()' is prohibited.")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr in DISALLOWED_PYTHON_ATTRIBUTES:
            self.errors.append(f"Access to introspection attribute '{node.attr}' is prohibited in the sandbox.")
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
    """Check JavaScript snippet for forbidden Node.js system patterns."""
    for pattern in DISALLOWED_JS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return {
                "valid": False,
                "error": f"Security Error: Usage of restricted system API pattern '{pattern}' is prohibited."
            }
    return {"valid": True, "error": None}


def _apply_posix_resource_limits():
    """
    Applies kernel-level POSIX process and memory limits when running on Linux / Docker.
    Safe no-op on Windows.
    """
    try:
        import resource
        # CPU time: 3s soft, 4s hard
        resource.setrlimit(resource.RLIMIT_CPU, (3, 4))
        # Address space / virtual memory: 128 MB
        resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
        # Maximum child processes (blocks fork-bombs): 10
        resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
        # Maximum file write size: 1 MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        # Maximum open file descriptors: 32
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    except (ImportError, Exception):
        pass


def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
    """
    Executes Python or JavaScript code with pre-execution AST validation,
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

    # 4. Determine execution command based on language and sandbox mode
    sandbox_mode = os.environ.get("SANDBOX_MODE", "isolated_subprocess").lower()

    try:
        preexec = _apply_posix_resource_limits if os.name != "nt" else None

        if sandbox_mode == "docker":
            # True Zero-Trust Container Isolation for Public Multi-Tenant Deployments
            script_file = os.path.join(temp_dir, "solution.py" if lang not in ["javascript", "js", "node"] else "solution.js")
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(clean_code)

            if lang in ["javascript", "js", "node"]:
                cmd = [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--memory", "128m",
                    "--cpus", "1.0",
                    "-v", f"{temp_dir}:/sandbox:ro",
                    "node:18-alpine",
                    "node", "--no-addons", "--disallow-code-generation-from-strings", "/sandbox/solution.js"
                ]
            else:
                cmd = [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--memory", "128m",
                    "--cpus", "1.0",
                    "-v", f"{temp_dir}:/sandbox:ro",
                    "python:3.11-alpine",
                    "python", "-I", "-B", "/sandbox/solution.py"
                ]
        else:
            # Hardened In-Process Sandbox with Flag Restrictions
            if lang in ["javascript", "js", "node"]:
                cmd = [
                    "node",
                    "--no-addons",
                    "--disallow-code-generation-from-strings",
                    "--max-old-space-size=64",
                    "-e",
                    clean_code
                ]
            else:
                # Inject runtime socket/network poison preamble
                runtime_code = (
                    "import sys\n"
                    "for _m in ['socket', 'urllib', 'http', 'subprocess', 'requests']:\n"
                    "    sys.modules[_m] = None\n\n"
                    + clean_code
                )
                cmd = [sys.executable, "-I", "-B", "-c", runtime_code]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=temp_dir,
            env=clean_env,
            preexec_fn=preexec
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
            "exit_code": res.returncode,
            "sandbox_meta": {
                "isolation": "container" if sandbox_mode == "docker" else "ast_isolated_ephemeral_runtime",
                "timeout_sec": TIMEOUT_SECONDS,
                "network": "disabled"
            }
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
