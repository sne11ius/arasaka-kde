#!/usr/bin/env python3

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from lib import arasaka_topology

FIXTURES = Path(__file__).with_name("fixtures") / "topology"


def load_outputs(name):
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)["outputs"]


def load_topology(name):
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)


class TopologyTest(unittest.TestCase):
    def test_classifies_embedded_connectors_as_internal(self):
        for connector in ("eDP-1", "LVDS-1", "DSI-1"):
            with self.subTest(connector=connector):
                self.assertEqual("internal", arasaka_topology.classify_output(connector))

        self.assertEqual("external", arasaka_topology.classify_output("DP-1"))

    def test_internal_only_uses_internal_as_primary(self):
        outputs = load_outputs("internal-only.json")

        self.assertEqual("eDP-1", arasaka_topology.choose_primary(outputs))

    def test_external_output_wins_over_internal_output(self):
        outputs = load_outputs("internal-external.json")

        self.assertEqual("DP-1", arasaka_topology.choose_primary(outputs))

    def test_external_only_plan_needs_no_priority_change(self):
        plan = arasaka_topology.build_plan(load_topology("external-only.json"))

        self.assertEqual("HDMI-A-1", plan["primary"])
        self.assertIsNone(plan["internal"])
        self.assertEqual([], plan["changes"])
        self.assertEqual(
            '{"enabled":["HDMI-A-1"],"internal":null,"primary":"HDMI-A-1"}',
            plan["signature"],
        )

    def test_multiple_external_outputs_keep_the_highest_priority_external(self):
        outputs = load_outputs("multiple-external.json")

        self.assertEqual("HDMI-A-1", arasaka_topology.choose_primary(outputs))

    def test_disabled_and_disconnected_outputs_are_ignored(self):
        topology = load_topology("disabled-outputs.json")

        plan = arasaka_topology.build_plan(topology)

        self.assertEqual("eDP-1", plan["primary"])
        self.assertEqual(
            '{"enabled":["eDP-1"],"internal":"eDP-1","primary":"eDP-1"}',
            plan["signature"],
        )

    def test_zero_enabled_outputs_is_rejected_as_transient(self):
        with self.assertRaises(arasaka_topology.NoEnabledOutputs):
            arasaka_topology.build_plan(load_topology("zero-enabled.json"))

    def test_priority_changes_only_promote_the_selected_primary(self):
        outputs = load_outputs("internal-external.json")

        self.assertEqual(
            [("DP-1", 1)], arasaka_topology.priority_changes(outputs)
        )

    def test_signature_is_stable_after_primary_priority_correction(self):
        before = load_outputs("internal-external.json")
        after = copy.deepcopy(before)
        after[0]["priority"] = 2
        after[1]["priority"] = 1

        self.assertEqual(
            arasaka_topology.topology_signature(before),
            arasaka_topology.topology_signature(after),
        )


if __name__ == "__main__":
    unittest.main()
