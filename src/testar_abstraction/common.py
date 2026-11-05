"""Comparison identities and bounded processing."""

import hashlib
import json
from decimal import Decimal


class AbstractionError(ValueError):
    """Invalid rules, evidence scope, or unsuitable comparison values."""


class AbstractionLimitError(AbstractionError):
    """The requested operation exceeds a processing limit."""


def canonical(value):
    if value is None or isinstance(value, (str, bool)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
        if not number.is_finite():
            raise AbstractionError("Comparison numbers must be finite")
        if number == 0:
            return "0"
        encoded = format(number, "f")
        return encoded.rstrip("0").rstrip(".") if "." in encoded else encoded
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return "{" + ",".join(canonical(key) + ":" + canonical(value[key])
                                for key in sorted(value)) + "}"
    raise AbstractionError("Comparison values must be JSON values")


def identity(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def run_key(source, run):
    return canonical([source, run])


def reference_key(reference):
    parts = [reference[key] for key in ("source", "run", "observation")]
    if "widget" in reference:
        parts.append(reference["widget"])
    return canonical(parts)


class Budget:
    def __init__(self):
        self.used = 0

    def account(self, value):
        self.used += len(canonical(value).encode("utf-8"))
        if self.used > 32 * 1024 * 1024:
            raise AbstractionLimitError("Comparison data exceeds 32 MiB")
