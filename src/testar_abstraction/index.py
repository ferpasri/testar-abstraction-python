"""Index only the selected test runs, retaining source-qualified references."""

from .common import AbstractionError, AbstractionLimitError, canonical, reference_key, run_key


def records(values):
    return list(values.values()) if isinstance(values, dict) else values


class EvidenceIndex:
    def __init__(self, sources, selected_runs):
        self.sources = {}
        self.observations = {}
        self.actions = {}
        self.executions = []
        self.selected_runs = []
        selected = {run_key(item["source"], item["run"]) for item in selected_runs}
        known = set()
        identities = set()
        fingerprints = set()
        widgets = 0
        for source in sorted(sources, key=lambda item: item["id"]):
            if source["id"] in identities or source["fingerprint"] in fingerprints:
                raise AbstractionError("Source identities and fingerprints must be unique")
            identities.add(source["id"])
            fingerprints.add(source["fingerprint"])
            evidence = {key: records(value) for key, value in source["evidence"].items()}
            sequences = {item["id"]: item["test_run"] for item in evidence["sequences"]}
            runs = {item["id"] for item in evidence["runs"]
                    if run_key(source["id"], item["id"]) in selected}
            known.update(run_key(source["id"], item["id"]) for item in evidence["runs"])
            if not runs:
                continue
            self.sources[source["id"]] = source
            self.selected_runs.extend({"source": source["id"], "run": run} for run in sorted(runs))
            for action in evidence["actions"]:
                self.actions[(source["id"], action["id"])] = action
            observations = sorted(evidence["observations"],
                                  key=lambda item: (item["test_sequence"], item["observation_index"], item["id"]))
            for observation in observations:
                run = sequences.get(observation["test_sequence"])
                if run is None:
                    raise AbstractionError("Observation refers to an unavailable sequence")
                if run not in runs:
                    continue
                reference = {"source": source["id"], "run": run, "observation": observation["id"]}
                key = reference_key(reference)
                if key in self.observations:
                    raise AbstractionError("Repeated observation identity")
                self.observations[key] = (reference, observation)
                widgets += len(observation["recorded_state"]["widgets"])
                if len(self.observations) > 10000 or widgets > 100000:
                    raise AbstractionLimitError("Selected observations or widgets exceed the processing limit")
            for record in evidence["executions"]:
                run = sequences.get(record["execution"]["test_sequence"])
                if run is None:
                    raise AbstractionError("Execution refers to an unavailable sequence")
                if run in runs:
                    self.executions.append((source["id"], run, record))
        if not selected <= known:
            raise AbstractionError("A selected run is unavailable")
        self.executions.sort(key=lambda item: (item[0], item[2]["execution"]["id"]))
