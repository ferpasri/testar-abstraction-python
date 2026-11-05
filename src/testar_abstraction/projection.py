"""State and widget projection, including filtering and hierarchy checks."""

from .common import AbstractionError, canonical
from .fields import project_fields, matches


def project_observation(observation, reference, definition, budget):
    state = observation["recorded_state"]
    values, informative = project_fields(state["properties"], definition["state"])
    comparison = {"state": values}
    if definition["capture"] == "same":
        comparison["capture"] = state["capture"]
    if "widgets" not in definition:
        return comparison, [], informative
    if state["capture"] == "unavailable":
        raise AbstractionError("Widget capture is unavailable")
    policy = definition["widgets"]
    widgets = state["widgets"]
    by_id = {widget["id"]: widget for widget in widgets}
    if len(by_id) != len(widgets):
        raise AbstractionError("Widget identities must be unique within an observation")
    paths = {}
    for widget in widgets:
        path = []
        current = widget
        while current is not None:
            if current["id"] in path:
                raise AbstractionError("Widget hierarchy contains a cycle")
            path.append(current["id"])
            if len(path) > 128:
                raise AbstractionError("Widget hierarchy exceeds depth 128")
            parent = current.get("parent")
            if parent is not None and parent not in by_id:
                raise AbstractionError("Widget parent is unavailable")
            current = by_id.get(parent)
        paths[widget["id"]] = path
    excluded = {widget["id"] for widget in widgets
                if any(matches(widget["properties"], predicate) for predicate in policy.get("exclude", []))}
    if policy["descendants"] == "exclude":
        excluded = {key for key, path in paths.items() if any(item in excluded for item in path)}
    selected = {}
    for widget in widgets:
        if widget["id"] in excluded:
            continue
        fields, useful = project_fields(widget["properties"], policy["fields"])
        informative |= useful
        selected[widget["id"]] = {"reference": {**reference, "widget": widget["id"]},
                                  "fields": fields, "description": fields, "informative": useful}
    if policy["hierarchy"] == "flat":
        descriptions = [item["fields"] for item in selected.values()]
    else:
        children = {}
        for key in selected:
            parent = next((ancestor for ancestor in paths[key][1:] if ancestor in selected), None)
            children.setdefault(parent, []).append(key)
        def serialize(parent, path):
            values = []
            for key in children.get(parent, []):
                item = selected[key]
                next_path = path + [item["fields"]]
                item["description"] = {"path": next_path}
                values.append({"fields": item["fields"], "children": serialize(key, next_path)})
            return sorted(values, key=canonical) if policy["order"] == "sort" else values
        descriptions = serialize(None, [])
    if policy["order"] == "sort":
        descriptions = sorted(descriptions, key=canonical)
    comparison["widgets"] = descriptions
    for item in selected.values():
        if item["informative"]:
            budget.account(item["description"])
    return comparison, list(selected.values()), informative
