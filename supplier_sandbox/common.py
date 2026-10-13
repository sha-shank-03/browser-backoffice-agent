"""Bounded data-only primitives, with typed errors that never echo input."""
import hashlib
import json
import re
from functools import wraps


class ContractError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def closed_errors(function):
    """Convert structural/type failures to a fixed code, never a raw input-bearing exception."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (TypeError, ValueError, KeyError, RecursionError, AttributeError):
            raise ContractError("invalid_contract_shape") from None
    return wrapped


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def bytes_sha(value):
    return hashlib.sha256(value).hexdigest()


def strict_json(raw, limit=65536):
    if not isinstance(raw, (bytes, str)) or len(raw if isinstance(raw, bytes) else raw.encode()) > limit:
        raise ContractError("body_bound")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate_json_key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ContractError("nonfinite_json")))
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("invalid_json") from None
    def visit(item, depth=0):
        if depth > 12:
            raise ContractError("json_depth")
        if isinstance(item, dict):
            for child in item.values():
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)
    visit(value)
    return value


def exact_keys(value, keys, code):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ContractError(code)


def bounded_text(value, code, maximum=160):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ContractError(code)
    return value


def hash_text(value, length=64):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value):
        raise ContractError("version_hash")
    return value
