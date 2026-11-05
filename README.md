# TESTAR Abstraction for Python

Construct abstract states, actions, and transitions from recorded test execution evidence. Rules select which captured properties participate in comparison.

## Install

Requires Python 3.11 or later. From this repository:

~~~powershell
python -m pip install .
~~~

Applications import `testar_abstraction`.

## Use

~~~python
from testar_abstraction import (
    parse_abstraction_rules, preview_abstraction, build_abstract_model,
)

rules = parse_abstraction_rules(rules_json)
preview = preview_abstraction(sources, rules, selected_runs)
abstract_model = build_abstract_model(preview, sources)
~~~

`sources` contains reconstructed evidence collections. `selected_runs` contains references such as `{"source": "source-id", "run": "run-id"}`. See the [API and input specification](docs/SPEC.md) for the collection structure and result fields.

A runnable [example](examples/construct_model.py) reads reconstructed input and rules files:

~~~powershell
python examples/construct_model.py input.json rules.json abstract-model.json
~~~

## Tests and package

Download the latest published shared cases, then run tests:

~~~powershell
python -m pip install -e .
python tools/prepare_conformance.py
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
~~~

Case preparation records the release and archive digest in `.cache/specs/current.json`. Tests verify file hashes before reading the prepared cases. [Compatibility metadata](compatibility.json) identifies the supported evidence format, rule language, and interpretation behavior.

Shared rules and cases are maintained in [TESTAR Abstraction Specs](https://github.com/ferpasri/testar-abstraction-specs). Remaining work is in [TODO](TODO.md).
