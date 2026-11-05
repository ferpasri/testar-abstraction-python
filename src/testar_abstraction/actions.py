"""Match available actions and executions within their abstract source states."""

from .common import AbstractionError, AbstractionLimitError, Budget, canonical, identity, reference_key
from .fields import project_fields, WHITESPACE


def selected(properties, fields):
    values, informative = project_fields(properties, fields)
    if fields and not informative:
        raise AbstractionError("No captured values for selected action fields")
    return sorted(values, key=lambda field: field["name"])


def project_action(index, reference, description, target, rules, parameters=None):
    action = index.actions.get((reference["source"], description))
    if action is None:
        raise AbstractionError("Original action description is unavailable")
    operation_fields, _ = project_fields(
        {"operation": action["action_type"]},
        [{"name": "operation", "keys": ["operation"], "transforms": rules.get("type", [])}],
    )
    operation = operation_fields[0]["reading"]["value"]
    if not operation.strip(WHITESPACE):
        raise AbstractionError("Normalized action type must contain text")
    target_values = []
    if rules.get("target"):
        observation = index.observations.get(reference_key(reference))
        widgets = observation[1]["recorded_state"]["widgets"] if observation else []
        widget = next((item for item in widgets if item["id"] == target), None)
        if widget is None:
            raise AbstractionError("Bound target widget is unavailable")
        target_values = selected(widget["properties"], rules["target"])
    inputs = []
    if "parameters" in rules:
        policy = rules["parameters"]
        inputs = selected(action["properties"] if parameters is None else parameters,
                          policy["available"] if parameters is None else policy["executed"])
    return {"operation": operation, "description": selected(action["properties"], rules.get("description", [])),
            "target": target_values, "parameters": inputs}


def build_action_evidence(index, nodes, rules):
    groups = {}
    bindings = {}
    seen = {}
    result = {"actions": [], "unmatchedAvailableActions": [], "unmatchedExecutions": []}
    budget = Budget()
    count = sum(len(observation["available_actions"]) for _, observation in index.observations.values())
    if count + len(index.executions) > 100000:
        raise AbstractionLimitError("Action comparison exceeds 100,000 records")

    def group_for(node, comparison):
        key = canonical([node, comparison])
        return groups.setdefault(key, {"id": identity([node, comparison]), "sourceNode": node,
                                        "comparison": comparison, "actionType": comparison["operation"],
                                        "availability": [], "executions": [], "ambiguous": False})

    for reference, observation in index.observations.values():
        node = nodes[reference_key(reference)]
        for available in observation["available_actions"]:
            action_reference = {**reference, "actionDescription": available["action_description"],
                                "targetWidget": available["target_widget"]}
            key = canonical(action_reference)
            if key in bindings:
                continue
            availability = {"reference": action_reference, "scope": observation["available_action_scope"],
                            "recordedExecutions": []}
            try:
                comparison = project_action(index, reference, available["action_description"],
                                            available["target_widget"], rules)
            except AbstractionError as error:
                result["unmatchedAvailableActions"].append({"reference": action_reference,
                    "sourceNode": node, "reason": str(error), "recordedExecutions": availability["recordedExecutions"]})
                bindings[key] = (None, availability)
                continue
            budget.account(comparison)
            group = group_for(node, comparison)
            observations = seen.setdefault(group["id"], set())
            if reference_key(reference) in observations:
                group["ambiguous"] = True
            observations.add(reference_key(reference))
            group["availability"].append(availability)
            bindings[key] = (group, availability)
    for source, run, record in index.executions:
        execution = record["execution"]
        reference = {"source": source, "run": run, "execution": execution["id"]}
        observation = {"source": source, "run": run, "observation": execution["source_observation"]}
        available_reference = {**observation, "actionDescription": execution["action_description"],
                               "targetWidget": execution["target_widget"]}
        binding = bindings.get(canonical(available_reference))
        if binding:
            binding[1]["recordedExecutions"].append(reference)
        recorded = [binding[1]["reference"]] if binding else []
        node = nodes.get(reference_key(observation))
        try:
            comparison = project_action(index, observation, execution["action_description"],
                                        execution["target_widget"], rules, execution["parameters"])
        except AbstractionError as error:
            comparison = None
            reason = str(error)
        if comparison is not None:
            budget.account(comparison)
        if node is None or comparison is None:
            result["unmatchedExecutions"].append({"reference": reference, "sourceNode": node,
                "reason": "Source observation is unavailable" if node is None else reason,
                "possibleActionIds": [binding[0]["id"]] if binding and binding[0] else [],
                "recordedAvailableActions": recorded})
            continue
        group = group_for(node, comparison)
        if group["ambiguous"] and (not binding or binding[0] is not group):
            result["unmatchedExecutions"].append({"reference": reference, "sourceNode": node,
                "reason": "Selected fields match multiple available actions in one observation",
                "possibleActionIds": [group["id"]], "recordedAvailableActions": recorded})
            continue
        item = {"reference": reference, "status": record["status"],
                "relationship": "recorded" if binding else "abstraction", "recordedAvailableActions": recorded}
        if binding and binding[0] is not None and binding[0] is not group:
            item["diagnostic"] = "Executed values differ from available-action values"
        group["executions"].append(item)
    result["actions"] = sorted(groups.values(), key=lambda group: group["id"])
    return result
