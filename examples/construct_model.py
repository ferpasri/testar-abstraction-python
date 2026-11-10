"""Construct a model from reconstructed evidence and a supplied rule definition."""

import argparse
import json
from decimal import Decimal
from pathlib import Path
from testar_abstraction.common import canonical
from testar_abstraction import parse_abstraction_rules, preview_abstraction, build_abstract_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Reconstructed sources and selected_runs JSON")
    parser.add_argument("rules", type=Path, help="Abstraction rule definition JSON")
    parser.add_argument("output", type=Path, help="Destination abstract model JSON")
    arguments = parser.parse_args()
    # Decimal retains the captured digits instead of rounding them to a float.
    data = json.loads(arguments.input.read_text(encoding="utf-8"), parse_float=Decimal)
    rules = parse_abstraction_rules(arguments.rules.read_text(encoding="utf-8"))
    preview = preview_abstraction(data["sources"], rules, data["selected_runs"])
    model = build_abstract_model(preview, data["sources"])
    arguments.output.write_text(canonical(model), encoding="utf-8")


if __name__ == "__main__":
    main()
