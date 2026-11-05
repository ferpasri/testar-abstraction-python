import copy
import json
import unittest
from testar_abstraction import preview_abstraction, build_abstract_model
from support import prepared, normalize, semantic_result


class SharedConformanceTests(unittest.TestCase):
    def test_published_cases(self):
        root, manifest = prepared()
        for suite, entry in manifest["suites"].items():
            for name in entry["cases"]:
                with self.subTest(suite=suite, case=name):
                    directory = root / entry["directory"] / name
                    data = json.loads((directory / "input.json").read_text(encoding="utf-8"))
                    definition = (directory / "rules.json").read_text(encoding="utf-8")
                    expected = normalize(json.loads((directory / "expected.json").read_text(encoding="utf-8")))
                    original = copy.deepcopy(data)
                    for reverse in (False, True):
                        if reverse:
                            data["sources"].reverse()
                            data["selected_runs"].reverse()
                            for source in data["sources"]:
                                for values in source["evidence"].values():
                                    values.reverse()
                        before = copy.deepcopy(data)
                        preview = preview_abstraction(data["sources"], definition, data["selected_runs"])
                        model = build_abstract_model(preview, data["sources"])
                        self.assertEqual(normalize(semantic_result(preview, model, suite)), expected)
                        self.assertEqual(data, before)
                    self.assertEqual(normalize(data), normalize(original))


if __name__ == "__main__":
    unittest.main()
