import copy
import json
from decimal import Decimal
import unittest
from testar_abstraction import (
    AbstractionError, AbstractionLimitError, parse_abstraction_rules,
    preview_abstraction, build_abstract_model,
)
from testar_abstraction.common import Budget, canonical
from testar_abstraction.fields import project_fields
from testar_abstraction.projection import project_observation
from support import prepared


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        root, _ = prepared()
        directory = root / "action-cases/available-and-executed"
        self.input = json.loads((directory / "input.json").read_text())
        self.rules = parse_abstraction_rules((directory / "rules.json").read_text())

    def preview(self):
        return preview_abstraction(self.input["sources"], self.rules, self.input["selected_runs"])

    def test_rejects_unknown_rules_and_mismatched_parameters(self):
        for definition in [
            {**self.rules, "execute_code": "anything"},
            {**self.rules, "actions": {"parameters": {
                "available": [{"name": "planned", "keys": ["value"]}],
                "executed": [{"name": "actual", "keys": ["value"]}],
            }}},
            {**self.rules, "state": self.rules["state"] * 2},
            {**self.rules, "version": True},
        ]:
            with self.subTest(definition=definition), self.assertRaises(AbstractionError):
                parse_abstraction_rules(definition)

    def test_rejects_changed_scope_and_repeated_members(self):
        preview = self.preview()
        changed = copy.deepcopy(self.input["sources"])
        changed[0]["fingerprint"] = "changed"
        with self.assertRaises(AbstractionError):
            build_abstract_model(preview, changed)
        preview["groups"][0]["members"].append(preview["groups"][0]["members"][0])
        with self.assertRaises(AbstractionError):
            build_abstract_model(preview, self.input["sources"])

    def test_rejects_unknown_selected_run_and_duplicate_sources(self):
        with self.assertRaises(AbstractionError):
            preview_abstraction(self.input["sources"], self.rules, [{"source": "missing", "run": "run"}])
        with self.assertRaises(AbstractionError):
            preview_abstraction(self.input["sources"] * 2, self.rules, self.input["selected_runs"])

    def test_action_comparison_is_optional_and_duplicate_availability_is_not_ambiguous(self):
        observation = self.input["sources"][0]["evidence"]["observations"][0]
        observation["available_actions"].append(copy.deepcopy(observation["available_actions"][0]))
        model = build_abstract_model(self.preview(), self.input["sources"])
        self.assertFalse(any(action["ambiguous"] for action in model["actionEvidence"]["actions"]))
        del self.rules["actions"]
        model = build_abstract_model(self.preview(), self.input["sources"])
        self.assertNotIn("actionEvidence", model)

    def test_limits_and_unsuitable_values(self):
        with self.assertRaises(AbstractionError):
            parse_abstraction_rules(" " * 65537)
        budget = Budget()
        with self.assertRaises(AbstractionLimitError):
            for _ in range(33):
                budget.account("x" * 1048576)
        with self.assertRaises(AbstractionError):
            project_fields({"text": 1}, [{"name": "text", "keys": ["text"], "transforms": [{"op": "trim"}]}])

    def test_numeric_comparison_preserves_types_and_precision(self):
        self.assertEqual(canonical(1), canonical(1.0))
        self.assertNotEqual(canonical(True), canonical(1))
        self.assertNotEqual(canonical("1"), canonical(1))
        self.assertNotEqual(canonical(1234567890123456789012345678901),
                            canonical(1234567890123456789012345678902))

    def test_json_reading_keeps_distinct_captured_values_separate(self):
        # Two captured measurements differ beyond ordinary floating-point precision.
        values = json.loads(
            '[1, 1.00, 18446744073709551615, 1.8446744073709551615e19, '
            '0.10000000000000000001, 0.10000000000000000002]',
            parse_float=Decimal)
        self.assertEqual(canonical(values[0]), canonical(values[1]))
        self.assertEqual(canonical(values[2]), canonical(values[3]))
        self.assertNotEqual(canonical(values[4]), canonical(values[5]))
        self.assertEqual(json.loads(canonical(values), parse_float=Decimal), values)

        # Numeric widget exclusions must retain the same precision as captured properties.
        definition = {
            "version": 1, "name": "Precise exclusion",
            "state": [{"name": "page", "keys": ["page"]}], "capture": "same",
            "widgets": {
                "fields": [{"name": "value", "keys": ["value"]}],
                "hierarchy": "flat", "order": "sort", "descendants": "keep",
                "exclude": [{"keys": ["value"], "op": "equals", "value": values[4]}],
            },
        }
        rules = parse_abstraction_rules(canonical(definition))
        self.assertEqual(rules["widgets"]["exclude"][0]["value"], values[4])
        observation = {"recorded_state": {
            "properties": {"page": "measurements"}, "capture": "complete",
            "widgets": [
                {"id": "excluded", "parent": None, "properties": {"value": values[4]}},
                {"id": "retained", "parent": None, "properties": {"value": values[5]}},
            ],
        }}
        _, widgets, _ = project_observation(
            observation, {"source": "source", "run": "run", "observation": "observation"},
            rules, Budget())
        self.assertEqual([item["reference"]["widget"] for item in widgets], ["retained"])

    def test_hierarchy_cycles_stay_unmatched(self):
        observation = self.input["sources"][0]["evidence"]["observations"][0]
        widget = observation["recorded_state"]["widgets"][0]
        widget["parent"] = widget["id"]
        self.rules["widgets"] = {"fields": [{"name": "name", "keys": ["ui.name"]}],
                                 "hierarchy": "tree", "order": "sort", "descendants": "keep"}
        self.assertTrue(self.preview()["unmatched"])


    def test_tree_filter_promotes_retained_children_and_can_exclude_descendants(self):
        observation = {
            "recorded_state": {"properties": {"page": "form"}, "capture": "complete", "widgets": [
                {"id": "root", "parent": None, "properties": {"name": "Window"}},
                {"id": "dynamic", "parent": "root", "properties": {"name": "Panel", "dynamic": True}},
                {"id": "child", "parent": "dynamic", "properties": {"name": "Submit"}},
            ]}
        }
        reference = {"source": "source", "run": "run", "observation": "observation"}
        rules = {"state": [{"name": "page", "keys": ["page"]}], "capture": "same",
                 "widgets": {"fields": [{"name": "name", "keys": ["name"]}],
                             "exclude": [{"keys": ["dynamic"], "op": "equals", "value": True}],
                             "hierarchy": "tree", "order": "sort", "descendants": "keep"}}
        comparison, widgets, _ = project_observation(observation, reference, rules, Budget())
        self.assertEqual(len(comparison["widgets"]), 1)
        self.assertEqual(len(comparison["widgets"][0]["children"]), 1)
        self.assertEqual([item["reference"]["widget"] for item in widgets], ["root", "child"])
        rules["widgets"]["descendants"] = "exclude"
        comparison, widgets, _ = project_observation(observation, reference, rules, Budget())
        self.assertEqual(comparison["widgets"][0]["children"], [])
        self.assertEqual([item["reference"]["widget"] for item in widgets], ["root"])

    def test_oversized_action_operation_remains_unmatched(self):
        self.input["sources"][0]["evidence"]["actions"][0]["action_type"] = "x" * 1048577
        model = build_abstract_model(self.preview(), self.input["sources"])
        self.assertTrue(model["actionEvidence"]["unmatchedAvailableActions"])
