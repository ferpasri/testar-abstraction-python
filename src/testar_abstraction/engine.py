"""Group observations using explicit comparison rules."""

from copy import deepcopy
from .common import AbstractionError, AbstractionLimitError, Budget, canonical, identity, reference_key
from .index import EvidenceIndex
from .projection import project_observation
from .rules import parse_abstraction_rules


def preview_abstraction(sources, definition, selected_runs):
    """Compare selected observations without changing the input records."""
    definition = parse_abstraction_rules(definition)
    index = EvidenceIndex(sources, selected_runs)
    groups = {}
    unmatched = []
    budget = Budget()
    for reference, observation in index.observations.values():
        try:
            comparison, widgets, informative = project_observation(observation, reference, definition, budget)
            if not informative:
                raise AbstractionError("None of the selected fields has a captured value")
        except AbstractionLimitError:
            raise
        except AbstractionError as error:
            unmatched.append({"reference": reference, "reason": str(error)})
            continue
        budget.account(comparison)
        key = canonical(comparison)
        group = groups.setdefault(key, {"id": identity([definition, comparison]), "comparison": comparison,
                                        "members": [], "widgetCorrespondences": []})
        group["members"].append({"reference": reference,
                                 "observationIndex": observation["observation_index"],
                                 "capture": observation["recorded_state"]["capture"]})
        group["widgetCorrespondences"].extend(widget for widget in widgets if widget["informative"])
    for group in groups.values():
        buckets = {}
        for widget in group["widgetCorrespondences"]:
            key = canonical(widget["description"])
            bucket = buckets.setdefault(key, {"description": widget["description"], "members": []})
            bucket["members"].append(widget["reference"])
        correspondences = []
        for key, bucket in sorted(buckets.items()):
            seen = set()
            ambiguous = False
            for reference in bucket["members"]:
                observation_key = reference_key({k: v for k, v in reference.items() if k != "widget"})
                ambiguous |= observation_key in seen
                seen.add(observation_key)
            correspondences.append({**bucket, "id": identity([group["id"], key]), "ambiguous": ambiguous})
        group["widgetCorrespondences"] = correspondences
    return deepcopy({"definition": definition, "policyFingerprint": identity(definition),
                     "interpreterVersion": "1.2.0",
                     "inputScope": {"sources": [{"id": source["id"], "label": source["label"],
                                                 "fingerprint": source["fingerprint"]}
                                                for source in index.sources.values()],
                                    "runs": index.selected_runs},
                     "groups": sorted(groups.values(), key=lambda group: group["id"]),
                     "unmatched": unmatched})
