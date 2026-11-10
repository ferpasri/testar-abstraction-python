"""Parse and validate rules before interpreting evidence."""

from copy import deepcopy
import json
from decimal import Decimal
from .common import AbstractionError, canonical


def require(condition, message):
    if not condition:
        raise AbstractionError(message)


def structure(value, required, optional=()):
    require(isinstance(value, dict), "Expected an object")
    require(set(required) <= value.keys() and value.keys() <= set(required) | set(optional),
            "Missing or unknown rule fields")


def text(value, maximum=256):
    require(isinstance(value, str) and 0 < len(value) <= maximum, "Expected bounded text")


def strings(value, maximum, minimum=0):
    require(isinstance(value, list) and minimum <= len(value) <= maximum, "Invalid string list")
    for item in value:
        text(item)


def transforms(items):
    require(isinstance(items, list) and len(items) <= 12, "Use at most 12 transforms")
    for item in items:
        require(isinstance(item, dict), "Expected a transform object")
        operation = item.get("op")
        if operation in ("trim", "collapse_whitespace", "lowercase"):
            structure(item, ["op"])
        elif operation == "replace":
            structure(item, ["op", "find", "with"])
            text(item["find"], 4096)
            require(isinstance(item["with"], str) and len(item["with"]) <= 4096, "Invalid replacement")
        elif operation == "map":
            structure(item, ["op", "values"])
            values = item["values"]
            require(isinstance(values, dict) and len(values) <= 128, "Invalid mapping")
            require(all(isinstance(k, str) and isinstance(v, str) and len(k) <= 4096
                        and len(v) <= 4096 for k, v in values.items()), "Invalid mapping text")
        elif operation == "url":
            structure(item, ["op"], ["remove_path_parameters", "remove_query", "remove_fragment"])
            for name in ("remove_path_parameters", "remove_query"):
                if name in item:
                    strings(item[name], 32)
            require("remove_fragment" not in item or type(item["remove_fragment"]) is bool,
                    "remove_fragment must be boolean")
        else:
            raise AbstractionError("Unknown transform")


def fields(items, minimum=0):
    require(isinstance(items, list) and minimum <= len(items) <= 32, "Invalid field count")
    names = set()
    for field in items:
        structure(field, ["name", "keys"], ["path", "required", "transforms"])
        text(field["name"])
        require(field["name"] not in names, "Field names must be unique")
        names.add(field["name"])
        strings(field["keys"], 8, 1)
        if "path" in field:
            strings(field["path"], 16, 1)
        require("required" not in field or type(field["required"]) is bool, "required must be boolean")
        transforms(field.get("transforms", []))


def parse_abstraction_rules(definition):
    """Return independent validated rules from JSON text or a mapping."""
    encoded = definition if isinstance(definition, str) else canonical(definition)
    require(len(encoded.encode("utf-8")) <= 65536, "Rules exceed 64 KiB")
    try:
        rule = json.loads(encoded, parse_float=Decimal)
    except ValueError as error:
        raise AbstractionError("Rules must be valid JSON") from error
    structure(rule, ["version", "name", "state", "capture"], ["widgets", "actions"])
    require(type(rule["version"]) is int and rule["version"] == 1, "Unsupported rule language")
    text(rule["name"])
    fields(rule["state"])
    require(rule["capture"] in ("same", "ignore"), "Unknown capture comparison")
    require(bool(rule["state"]) or "widgets" in rule, "Select state or widget fields")
    if "widgets" in rule:
        widgets = rule["widgets"]
        structure(widgets, ["fields", "hierarchy", "order", "descendants"], ["exclude"])
        fields(widgets["fields"], 1)
        require(widgets["hierarchy"] in ("flat", "tree"), "Unknown hierarchy")
        require(widgets["order"] in ("sort", "preserve"), "Unknown widget order")
        require(widgets["descendants"] in ("keep", "exclude"), "Unknown descendant rule")
        predicates = widgets.get("exclude", [])
        require(isinstance(predicates, list) and len(predicates) <= 32, "Invalid exclusion count")
        for predicate in predicates:
            require(isinstance(predicate, dict), "Expected predicate")
            operation = predicate.get("op")
            require(operation in ("present", "equals", "contains"), "Unknown predicate")
            structure(predicate, ["keys", "op"] + ([] if operation == "present" else ["value"]))
            strings(predicate["keys"], 8, 1)
            if operation == "contains":
                require(isinstance(predicate["value"], str) and len(predicate["value"]) <= 4096,
                        "Invalid contains value")
    if "actions" in rule:
        actions = rule["actions"]
        structure(actions, [], ["type", "description", "target", "parameters"])
        transforms(actions.get("type", []))
        for key in ("description", "target"):
            fields(actions.get(key, []))
        if "parameters" in actions:
            parameters = actions["parameters"]
            structure(parameters, ["available", "executed"])
            fields(parameters["available"])
            fields(parameters["executed"])
            require({f["name"] for f in parameters["available"]} ==
                    {f["name"] for f in parameters["executed"]}, "Parameter fields need the same names")
    return deepcopy(rule)
