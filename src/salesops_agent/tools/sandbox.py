import ast
import builtins
import contextlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from io import StringIO
from typing import Any, Dict, Optional

from ..config.settings import settings
from ..policies import POLICY_SANDBOX

FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
    "exit",
    "quit",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "memoryview",
}

FORBIDDEN_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "pathlib",
    "shutil",
    "ctypes",
    "multiprocessing",
    "threading",
    "importlib",
    "inspect",
    "pickle",
    "shelve",
    "sqlite3",
    "ssl",
    "asyncio",
}

RESTRICTED_DATA_MARKERS = (
    "internal_hr_data",
    "internal_financial_data",
    "confidential_m_and_a",
    "confidential_layoff",
    "salary_usd",
    "equity_bonus_usd",
)


class SandboxDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _SandboxVisitor(ast.NodeVisitor):
    def __init__(self, allowed_modules: set[str]):
        self.allowed_modules = allowed_modules

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.module:
            raise SandboxDenied("relative imports are not allowed")
        self._check_module(node.module)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_NAMES:
            raise SandboxDenied(f"call to '{func.id}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id in FORBIDDEN_MODULES:
            raise SandboxDenied(f"access to '{node.value.id}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            raise SandboxDenied(f"use of '{node.id}' is not allowed")
        self.generic_visit(node)

    def _check_module(self, module_name: str) -> None:
        root = module_name.split(".")[0]
        if root in FORBIDDEN_MODULES or root not in self.allowed_modules:
            raise SandboxDenied(f"import of '{module_name}' is not allowed")


class SandboxedCodeExecutor:
    """Restricted CRM analysis environment — no host eval/exec, no network, no HR data."""

    def __init__(self):
        self.timeout = settings.sandbox_timeout_seconds
        self.allowed_modules = set(settings.sandbox_allowed_modules)

    def execute(self, code: str, data_context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._validate(code)
            output, result = self._run_isolated(code, data_context)
            return {
                "status": "success",
                "success": True,
                "output": output,
                "result": result,
            }
        except SandboxDenied as exc:
            return {
                "status": "blocked",
                "success": False,
                "blocked": True,
                "reason": exc.reason,
                "policy": POLICY_SANDBOX,
                "output": None,
            }
        except FuturesTimeout:
            return {
                "status": "blocked",
                "success": False,
                "blocked": True,
                "reason": f"execution exceeded {self.timeout} seconds",
                "policy": POLICY_SANDBOX,
                "output": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "success": False,
                "reason": f"execution error: {exc}",
                "policy": POLICY_SANDBOX,
                "output": None,
            }

    def _validate(self, code: str) -> None:
        lowered = code.lower()
        for marker in RESTRICTED_DATA_MARKERS:
            if marker in lowered:
                raise SandboxDenied("restricted_internal_data")

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise SandboxDenied(f"invalid analysis code: {exc}") from exc

        _SandboxVisitor(self.allowed_modules).visit(tree)

    def _run_isolated(self, code: str, data_context: Dict[str, Any]):
        allowed = self.allowed_modules

        def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".")[0]
            if root in FORBIDDEN_MODULES or root not in allowed:
                raise SandboxDenied(f"import of '{name}' is not allowed")
            return builtins.__import__(name, globals, locals, fromlist, level)

        safe_builtins = {
            name: getattr(builtins, name)
            for name in (
                "abs", "all", "any", "bool", "dict", "enumerate", "filter",
                "float", "int", "len", "list", "max", "min", "print", "range",
                "round", "set", "sorted", "str", "sum", "tuple", "zip", "map",
            )
        }
        safe_builtins["__import__"] = _safe_import
        safe_globals: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            **data_context,
        }
        for module_name in self.allowed_modules:
            try:
                safe_globals[module_name] = __import__(module_name)
            except ImportError:
                continue

        compiled = compile(code, "<sandbox>", "exec")
        buffer = StringIO()

        def _target():
            with contextlib.redirect_stdout(buffer):
                exec(compiled, safe_globals, safe_globals)  # noqa: S102 — restricted after AST allowlist
            return safe_globals.get("result")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_target)
            result = future.result(timeout=self.timeout)
        return buffer.getvalue(), result


def analyze_crm_data(analysis_code: str, account_id: Optional[str] = None) -> Dict[str, Any]:
    from ..data.loader import DataLoader

    data = DataLoader()
    context = {
        "accounts": data.accounts,
        "opportunities": data.opportunities,
        "contacts": data.contacts,
        "activities": data.activities,
        "tickets": data.support_tickets,
        "usage": data.product_usage,
    }
    if account_id:
        context["accounts"] = [a for a in context["accounts"] if a.get("account_id") == account_id]

    return SandboxedCodeExecutor().execute(analysis_code, context)
