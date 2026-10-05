"""Small AST-restricted worker for synthetic clamp output; no generated imports/IO."""
from __future__ import annotations

import ast
import json
import re
import sys


def source_text(answer):
    match = re.fullmatch(r"\s*```(?:python|py)?\s*\n(.*?)\n```\s*", answer, re.DOTALL)
    return match[1] if match else answer.strip()


def check_source(source, kind):
    if kind not in {"function", "assertions"} or len(source) > 8192:
        return "invalid_input"
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return "invalid_syntax"
    nodes = list(ast.walk(tree))
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.If, ast.IfExp,
        ast.Return, ast.Raise, ast.Call, ast.Name, ast.Load, ast.Store, ast.Constant,
        ast.Compare, ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq, ast.BoolOp,
        ast.And, ast.Or, ast.UnaryOp, ast.USub, ast.Not, ast.Expr, ast.Assert,
        ast.Try, ast.ExceptHandler, ast.Assign, ast.Subscript, ast.Attribute)
    calls = {"ValueError", "min", "max"} if kind == "function" else {"clamp", "str"}
    if len(nodes) > 256 or any(not isinstance(node, allowed) for node in nodes):
        return "unsafe_structure"
    for node in nodes:
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return "unsafe_name"
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in calls):
            return "unsafe_call"
        if isinstance(node, ast.Attribute) and (kind != "assertions" or node.attr != "args"):
            return "unsafe_attribute"
    if kind == "function":
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            return "function_only_required"
        function = tree.body[0]
        if (function.name != "clamp" or function.decorator_list or function.args.defaults
                or function.args.kw_defaults or function.args.vararg or function.args.kwarg
                or function.args.kwonlyargs or function.args.posonlyargs
                or [a.arg for a in function.args.args] != ["value", "lower", "upper"]
                or sum(isinstance(n, ast.FunctionDef) for n in nodes) != 1):
            return "invalid_signature"
    else:
        if any(isinstance(n, ast.FunctionDef) for n in nodes):
            return "assertions_only_required"
        expected = ["assert clamp(-2, 0, 3) == 0", "assert clamp(2, 0, 3) == 2",
                    "assert clamp(5, 0, 3) == 3", "assert clamp(8, 4, 4) == 4"]
        actual = {ast.dump(n) for n in nodes if isinstance(n, ast.Assert)}
        if not all(ast.dump(ast.parse(item).body[0]) in actual for item in expected):
            return "missing_exact_assertions"
        reversed_call = ast.dump(ast.parse("clamp(2, 3, 0)").body[0].value)
        tries = [n for n in nodes if isinstance(n, ast.Try)]
        if not any(any(isinstance(n, ast.Call) and ast.dump(n) == reversed_call for n in ast.walk(t))
                   and any(isinstance(h.type, ast.Name) and h.type.id == "ValueError" for h in t.handlers)
                   and any(isinstance(n, ast.Assert) and isinstance(n.test, ast.Constant)
                           and n.test.value is False and isinstance(n.msg, ast.Constant)
                           and n.msg.value == "expected ValueError" for statement in (*t.body, *t.orelse)
                           for n in ast.walk(statement)) for t in tries):
            return "missing_reversed_bounds_check"
    code = compile(tree, "<synthetic-clamp>", "exec")
    builtins = {"ValueError": ValueError, "AssertionError": AssertionError,
                "min": min, "max": max, "int": int, "str": str}
    def clamp(value, lower, upper):
        if lower > upper: raise ValueError("lower exceeds upper")
        return min(max(value, lower), upper)
    try:
        namespace = {"__builtins__": builtins, "clamp": clamp}
        exec(code, namespace)
        if kind == "function":
            function = namespace["clamp"]
            for args, expected in [((-2, 0, 3), 0), ((2, 0, 3), 2), ((5, 0, 3), 3),
                ((8, 4, 4), 4), ((4, 4, 4), 4), ((0, 0, 3), 0), ((3, 0, 3), 3),
                ((-4, -5, -1), -4), ((-8, -5, -1), -5)]:
                if function(*args) != expected: return "incorrect_value"
            try: function(2, 3, 0)
            except ValueError as error:
                if str(error) != "lower exceeds upper": return "incorrect_error_message"
            else: return "missing_value_error"
        else:
            # A check suite must detect wrong messages and absent exceptions.
            for wrong in (lambda v, lo, hi: 2,):
                try: exec(code, {"__builtins__": builtins, "clamp": wrong})
                except AssertionError: pass
                else: return "checks_accept_wrong_values"
            def incorrect_error(v, lo, hi):
                if lo > hi: raise ValueError("incorrect")
                return clamp(v, lo, hi)
            def absent_error(v, lo, hi): return 2 if lo > hi else clamp(v, lo, hi)
            for wrong in (incorrect_error, absent_error):
                try: exec(code, {"__builtins__": builtins, "clamp": wrong})
                except AssertionError: pass
                else: return "checks_accept_wrong_error"
    except Exception:
        return "execution_failed"
    return None


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read(16384))
        reason = check_source(payload["source"], payload["kind"])
        print(json.dumps({"passed": reason is None, "reason": reason}))
    except Exception:
        print('{"passed":false,"reason":"worker_failed"}')
