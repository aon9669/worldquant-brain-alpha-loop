#!/usr/bin/env python3
"""Local Fast Expression syntax/AST precheck for WorldQuant BRAIN."""
import json, re, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent

def load_operators():
    p = ROOT / "operators.json"
    if not p.exists():
        return set()
    data = json.loads(p.read_text())
    return {o["name"] for o in data if isinstance(o, dict) and "name" in o}

def load_fields():
    fields = set()
    for p in [
        ROOT / "fields_cache" / "summary.json",
        WORK / "wqb_data_fields_summary.json",
        WORK / "tool" / "wqb_data_fields_summary.json",
    ]:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, list):
                    for x in data:
                        if isinstance(x, dict) and "id" in x:
                            fields.add(x["id"])
                        elif isinstance(x, str):
                            fields.add(x)
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list):
                            for x in v:
                                if isinstance(x, dict) and "id" in x:
                                    fields.add(x["id"])
                                elif isinstance(x, str):
                                    fields.add(x)
                        elif isinstance(k, str):
                            fields.add(k)
            except Exception:
                pass
    # common PV + group fields always allowed
    fields.update({
        "close", "open", "high", "low", "vwap", "volume", "returns",
        "adv20", "cap", "sharesout", "sector", "industry", "subindustry",
        "country", "exchange", "market", "currency", "split",
    })
    # category files
    cat = ROOT / "fields_cache" / "categories.json"
    if cat.exists():
        try:
            d = json.loads(cat.read_text())
            for v in d.values():
                if isinstance(v, list):
                    fields.update(v)
        except Exception:
            pass
    return fields

# rough arity: min args (None = any)
ARITY = {
    "abs": 1, "log": 1, "sqrt": 1, "sign": 1, "reverse": 1, "rank": 1, "zscore": 1,
    "scale": 1, "winsorize": (1, 2), "signed_power": 2,
    "add": (2, 99), "subtract": 2, "multiply": (2, 99), "divide": 2,
    "max": (2, 99), "min": (2, 99), "power": 2,
    "if_else": 3, "trade_when": 3,
    "ts_rank": 2, "ts_zscore": 2, "ts_delta": 2, "ts_delay": 2, "ts_mean": 2,
    "ts_std_dev": 2, "ts_sum": 2, "ts_product": 2, "ts_corr": 3, "ts_covariance": 3,
    "ts_decay_linear": 2, "ts_backfill": 2, "ts_arg_max": 2, "ts_arg_min": 2,
    "ts_av_diff": 2, "ts_scale": 2, "ts_quantile": (2, 3), "ts_count_nans": 2,
    "ts_regression": (3, 5), "ts_step": (0, 1),
    "group_rank": 2, "group_neutralize": 2, "group_zscore": 2, "group_mean": 3,
    "vec_avg": 1, "vec_sum": 1, "bucket": (1, 3),
}

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

def tokenize_calls(expr: str):
    """Find func_name( occurrences."""
    return re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr)

def balanced_parens(expr: str):
    depth = 0
    for c in expr:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0

def split_top_args(inner: str):
    args, depth, cur, in_str = [], 0, [], False
    quote = None
    for c in inner:
        if in_str:
            cur.append(c)
            if c == quote:
                in_str = False
            continue
        if c in ('"', "'"):
            in_str = True
            quote = c
            cur.append(c)
            continue
        if c == "(":
            depth += 1
            cur.append(c)
        elif c == ")":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if cur or (inner and inner.strip().endswith(",")):
        args.append("".join(cur).strip())
    return [a for a in args if a != ""]

def find_call_spans(expr: str):
    """Yield (name, arg_string) for each call via simple scan."""
    out = []
    i = 0
    n = len(expr)
    while i < n:
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", expr[i:])
        if m:
            name = m.group(1)
            start = i + m.end()  # after '('
            depth = 1
            j = start
            while j < n and depth:
                if expr[j] == "(":
                    depth += 1
                elif expr[j] == ")":
                    depth -= 1
                j += 1
            inner = expr[start:j - 1]
            out.append((name, inner))
            i = start
        else:
            i += 1
    return out

def extract_field_candidates(expr: str, ops: set):
    """Identifiers that are not operators and not keywords/numbers."""
    skip = ops | {"true", "false", "True", "False", "and", "or", "not", "in", "std", "filter", "range"}
    ids = set(IDENT.findall(expr))
    # remove those used as function names
    for name, _ in find_call_spans(expr):
        ids.discard(name)
    # remove keyword-like kwarg names appearing as name=
    for kw in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", expr):
        ids.discard(kw)
    return {x for x in ids if x not in skip and not x.isupper() or x in {"USA"}} - skip

def check_expression(expr: str):
    errors = []
    expr = (expr or "").strip()
    if not expr:
        return {"ok": False, "errors": ["empty expression"]}
    if not balanced_parens(expr):
        errors.append("unbalanced parentheses")
    ops = load_operators()
    fields = load_fields()
    calls = find_call_spans(expr)
    for name, inner in calls:
        if name not in ops:
            # allow arithmetic aliases sometimes written as functions only if in ops
            errors.append(f"unknown operator: {name}")
            continue
        args = split_top_args(inner)
        # filter out kwarg-only trailing empties
        arity = ARITY.get(name)
        if arity is not None:
            n = len(args)
            if isinstance(arity, tuple):
                lo, hi = arity
                if n < lo or n > hi:
                    errors.append(f"{name}: expected {lo}-{hi} args, got {n}")
            else:
                if n != arity:
                    # winsorize etc may have kwargs; count positional-ish
                    pos = [a for a in args if "=" not in a]
                    if len(pos) != arity and not (isinstance(arity, int) and len(pos) >= 1 and name in {"winsorize", "scale", "bucket"}):
                        if name in {"winsorize", "scale", "bucket"} and len(pos) >= 1:
                            pass
                        else:
                            errors.append(f"{name}: expected {arity} args, got {n} (positional {len(pos)})")
        # ts_* second arg should look numeric when present
        if name.startswith("ts_") and name not in {"ts_step"} and args:
            if len(args) >= 2:
                a1 = args[1].strip()
                if name in {"ts_corr", "ts_covariance", "ts_regression"}:
                    # last numeric window often
                    pass
                elif not re.match(r"^-?\d+(\.\d+)?$", a1) and "=" not in a1:
                    # allow expressions but warn soft — only hard-fail clearly non-numeric words that aren't numbers
                    if re.match(r"^[A-Za-z_]", a1) and not a1.replace("_", "").isalnum() == False:
                        # soft: skip
                        pass

    # field check: identifiers not operators
    cand = extract_field_candidates(expr, ops)
    # also strip pure numbers already not in IDENT
    unknown = sorted(c for c in cand if c not in fields)
    # group names are ok
    group_ok = {"sector", "industry", "subindustry", "country", "exchange", "market"}
    unknown = [u for u in unknown if u not in group_ok]
    if unknown:
        errors.append("unknown field ids: " + ", ".join(unknown[:20]))

    return {"ok": len(errors) == 0, "errors": errors, "operators_used": sorted({n for n, _ in calls}), "fields_guess": sorted(cand)}

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "errors": ["usage: precheck.py <expression|->"]}))
        sys.exit(2)
    if sys.argv[1] == "-":
        expr = sys.stdin.read()
    elif sys.argv[1] == "--file" and len(sys.argv) >= 3:
        expr = Path(sys.argv[2]).read_text()
    else:
        expr = sys.argv[1]
    # allow expression passed as remaining args
    if len(sys.argv) > 2 and sys.argv[1] not in ("-", "--file"):
        expr = " ".join(sys.argv[1:])
    result = check_expression(expr)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)

if __name__ == "__main__":
    main()
