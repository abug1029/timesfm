"""goal success_condition 安全求值: ast 白名单, 无调用无属性访问"""
import ast

def _safe_min(*args):
    if len(args) == 1 and hasattr(args[0], "__iter__") and not isinstance(args[0], (str, bytes)):
        seq = list(args[0])
        if not seq:
            raise _Unmet("min of empty sequence")
        return min(seq)
    return min(args)

def _safe_max(*args):
    if len(args) == 1 and hasattr(args[0], "__iter__") and not isinstance(args[0], (str, bytes)):
        seq = list(args[0])
        if not seq:
            raise _Unmet("max of empty sequence")
        return max(seq)
    return max(args)

class _Unmet(Exception):
    pass

_ALLOWED_FUNCS = {"len": len, "min": _safe_min, "max": _safe_max, "all": all, "any": any,
                  "abs": abs, "round": round}

def _forbidden_nodes(tree, allowed_names):
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            bad.append("attribute access at line %s" % getattr(node, "lineno", "?"))
        elif isinstance(node, (ast.Lambda, ast.Await, ast.NamedExpr)):
            bad.append("lambda/await/walrus forbidden")
        elif isinstance(node, ast.Call):
            f = node.func
            if not (isinstance(f, ast.Name) and f.id in _ALLOWED_FUNCS):
                bad.append("call to non-whitelisted func at line %s" % getattr(node, "lineno", "?"))
        elif isinstance(node, ast.Name) and node.id not in allowed_names:
            bad.append("name %s not in snapshot or allowed funcs" % node.id)
    return bad

def evaluate_goal(conditions, snapshot):
    allowed_names = set(snapshot) | set(_ALLOWED_FUNCS)
    ok_flags, reasons = [], []
    for expr in conditions:
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as e:
            ok_flags.append(False)
            reasons.append("%s -> parse error: %s" % (expr, e))
            continue
        bad = _forbidden_nodes(tree, allowed_names)
        if bad:
            ok_flags.append(False)
            reasons.append("%s -> forbidden: %s" % (expr, bad))
            continue
        try:
            val = eval(compile(tree, "<goal>", "eval"),
                       {"__builtins__": {}},
                       dict(snapshot) | {k: _ALLOWED_FUNCS[k] for k in _ALLOWED_FUNCS})
        except _Unmet as u:
            ok_flags.append(False)
            reasons.append("%s -> unmet (%s)" % (expr, u))
            continue
        except Exception as any_err:
            ok_flags.append(False)
            reasons.append("%s -> eval error: %s" % (expr, any_err))
            continue
        ok_flags.append(val is True)
        if val is not True:
            reasons.append("%s -> unmet (val=%r)" % (expr, val))
    return all(ok_flags), reasons
