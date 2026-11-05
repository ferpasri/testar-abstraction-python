"""Construct a model from reconstructed evidence and a supplied rule definition."""

import argparse
import json
from pathlib import Path
from testar_abstraction import parse_abstraction_rules, preview_abstraction, build_abstract_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Reconstructed sources and selected_runs JSON")
    parser.add_argument("rules", type=Path, help="Abstraction rule definition JSON")
    parser.add_argument("output", type=Path, help="Destination abstract model JSON")
    arguments = parser.parse_args()
    data = json.loads(arguments.input.read_text(encoding="utf-8"))
    rules = parse_abstraction_rules(arguments.rules.read_text(encoding="utf-8"))
    preview = preview_abstraction(data["sources"], rules, data["selected_runs"])
    model = build_abstract_model(preview, data["sources"])
    arguments.output.write_text(json.dumps(model, ensure_ascii=False, indent=4), encoding="utf-8")


if __name__ == "__main__":
    main()
