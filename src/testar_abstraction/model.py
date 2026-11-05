"""Construct abstract transitions and retain the evidence supporting each link."""

from copy import deepcopy
from .common import AbstractionError, canonical, identity, reference_key
from .index import EvidenceIndex
from .actions import build_action_evidence


def build_abstract_model(preview, sources):
    """Construct a model from a preview and its unchanged original sources."""
    requested = preview["inputScope"]["sources"]
    scoped = []
    for source in requested:
        matches = [item for item in sources if item["id"] == source["id"]]
        if len(matches) != 1 or matches[0]["fingerprint"] != source["fingerprint"]:
            raise AbstractionError("Original evidence is missing or its fingerprint has changed")
        scoped.append(matches[0])
    index = EvidenceIndex(scoped, preview["inputScope"]["runs"])
    nodes = []
    by_observation = {}
    identifiers = set()
    for group in preview["groups"]:
        if not group["members"] or group["id"] in identifiers:
            raise AbstractionError("Groups need distinct identities and original observations")
        identifiers.add(group["id"])
        members = [member["reference"] for member in group["members"]]
        for reference in members:
            key = reference_key(reference)
            if key not in index.observations or key in by_observation:
                raise AbstractionError("Group observation is unavailable or repeated")
            by_observation[key] = group["id"]
        nodes.append({"id": group["id"], "groupId": group["id"], "members": members})
    reasons = {reference_key(item["reference"]): item["reason"] for item in preview["unmatched"]}
    for key, (reference, _) in index.observations.items():
        if key not in by_observation:
            node = "unmatched:" + key
            by_observation[key] = node
            nodes.append({"id": node, "members": [reference],
                          "unmatchedReason": reasons.get(key, "Observation was not grouped")})
    action_evidence = None
    action_by_execution = {}
    if "actions" in preview["definition"]:
        action_evidence = build_action_evidence(index, by_observation, preview["definition"]["actions"])
        for action in action_evidence["actions"]:
            for execution in action["executions"]:
                action_by_execution[canonical(execution["reference"])] = action
    edges = {}
    unlinked = []
    completed = set()

    def edge(kind, origin, target, operation=None, action=None, unique=None):
        key = canonical([kind, origin, target, operation, unique])
        if key not in edges:
            item = {"id": identity(key), "kind": kind, "source": origin, "target": target,
                    "executions": [], "orderLinks": []}
            if operation is not None:
                item["actionType"] = operation
            if action is not None:
                item["abstractAction"] = action["id"]
            edges[key] = item
        return edges[key]

    for source, run, record in index.executions:
        execution = record["execution"]
        reference = {"source": source, "run": run, "execution": execution["id"]}
        origin = {"source": source, "run": run, "observation": execution["source_observation"]}
        target = {"source": source, "run": run, "observation": record.get("resultingObservation", "")}
        origin_node = by_observation.get(reference_key(origin))
        target_node = by_observation.get(reference_key(target))
        description = index.actions.get((source, execution["action_description"]))
        if record["status"] == "completed" and record.get("resultingObservation"):
            completed.add((reference_key(origin), reference_key(target)))
        if record["status"] != "completed" or origin_node is None or target_node is None or description is None:
            unlinked.append({"reference": reference, "sourceNode": origin_node, "status": record["status"],
                             "reason": "Execution has no completed connection in the selected evidence"})
            continue
        action = action_by_execution.get(canonical(reference))
        operation = action["actionType"] if action else description["action_type"]
        unique = (action["id"] if action else reference) if action_evidence is not None else None
        edge("execution", origin_node, target_node, operation, action, unique)["executions"].append(reference)
    sequences = {}
    for reference, observation in index.observations.values():
        sequences.setdefault((reference["source"], observation["test_sequence"]), []).append((reference, observation))
    for observations in sequences.values():
        observations.sort(key=lambda item: item[1]["observation_index"])
        for (origin, _), (target, _) in zip(observations, observations[1:]):
            if (reference_key(origin), reference_key(target)) not in completed:
                edge("observation_order", by_observation[reference_key(origin)],
                     by_observation[reference_key(target)])["orderLinks"].append({"source": origin, "target": target})
    result = {"nodes": sorted(nodes, key=lambda node: node["id"]),
              "edges": sorted(edges.values(), key=lambda item: item["id"]), "unlinkedExecutions": unlinked}
    if action_evidence is not None:
        result["actionEvidence"] = action_evidence
    return deepcopy(result)
