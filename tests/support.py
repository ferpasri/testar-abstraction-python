"""Read prepared published fixtures and project implementation results for comparison."""

import hashlib
import json
from pathlib import Path
from testar_abstraction.common import canonical

ROOT = Path(__file__).resolve().parents[1]


def prepared():
    cache = ROOT / ".cache/specs"
    if not (cache / "current.json").exists():
        raise RuntimeError("Run python tools/prepare_conformance.py before the shared tests")
    selection = json.loads((cache / "current.json").read_text())
    directory = (cache / selection["directory"]).resolve()
    if not directory.is_relative_to(cache.resolve()):
        raise RuntimeError("Unsafe conformance cache selection")
    for name, digest in selection["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Prepared conformance data changed: " + name)
    manifest = json.loads((directory / "conformance/manifest.json").read_text())
    compatibility = json.loads((ROOT / "compatibility.json").read_text())
    if any(manifest.get(key) != value for key, value in compatibility.items()):
        raise RuntimeError("Unsupported conformance behavior")
    return directory / "conformance", manifest


def normalize(value):
    if isinstance(value, list):
        return sorted((normalize(item) for item in value), key=canonical)
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


def semantic_result(preview, model, suite):
    members = {node["id"]: node["members"] for node in model["nodes"]}
    if suite == "states":
        return {"groups": [[member["reference"] for member in group["members"]] for group in preview["groups"]],
                "unmatched": [item["reference"] for item in preview["unmatched"]],
                "transitions": [{"from": members[edge["source"]], "to": members[edge["target"]],
                                  "action_type": edge["actionType"], "executions": edge["executions"]}
                                 for edge in model["edges"] if edge["kind"] == "execution"],
                "observation_order_links": [link for edge in model["edges"] for link in edge["orderLinks"]],
                "unlinked_executions": [{"reference": item["reference"], "status": item["status"]}
                                        for item in model["unlinkedExecutions"]],
                "widget_correspondences": [{"members": item["members"], "ambiguous": item["ambiguous"]}
                                          for group in preview["groups"] for item in group["widgetCorrespondences"]]}
    evidence = model["actionEvidence"]
    return {"actions": [{"state": members[action["sourceNode"]], "comparison": action["comparison"],
                          "availability": action["availability"],
                          "executions": [{**item, "diagnostic": bool(item.get("diagnostic"))} for item in action["executions"]],
                          "ambiguous": action["ambiguous"]} for action in evidence["actions"]],
            "unmatched_available": [{"reference": item["reference"], "state": members[item["sourceNode"]],
                                      "recordedExecutions": item["recordedExecutions"], "diagnostic": bool(item["reason"])}
                                     for item in evidence["unmatchedAvailableActions"]],
            "unmatched_executions": [{"reference": item["reference"], "diagnostic": bool(item["reason"]),
                                       "possible_actions": len(item["possibleActionIds"]),
                                       "recordedAvailableActions": item["recordedAvailableActions"]}
                                      for item in evidence["unmatchedExecutions"]],
            "transitions": [{"executions": edge["executions"], "matched_action": "abstractAction" in edge}
                            for edge in model["edges"] if edge["kind"] == "execution"]}
