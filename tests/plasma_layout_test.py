#!/usr/bin/env python3

import json
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT = REPO_ROOT / "plasma" / "layout.js"
HARNESS = Path(__file__).with_name("plasma_layout_harness.js")
LAUNCHER = "com.arasaka.launcher"


def run_layout(**options):
    completed = subprocess.run(
        ["node", str(HARNESS), str(LAYOUT), json.dumps(options)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


def hosts(snapshot):
    return [
        (desktop, widget)
        for desktop in snapshot["desktops"]
        for widget in desktop["widgets"]
        if widget["type"] == LAUNCHER
        and str(widget["config"].get("Arasaka/Managed")).lower() == "true"
    ]


class PlasmaLayoutTest(unittest.TestCase):
    def test_loading_host_keeps_bars_until_native_children_are_ready(self):
        model = run_layout(notReady=True, becomesReady=True)
        self.assertIsNotNone(model["first"]["error"])
        self.assertEqual(model["initial"]["panels"], model["first"]["panels"])
        self.assertEqual(1, len(hosts(model["first"])))
        self.assertIsNone(model["second"]["error"])
        self.assertEqual(model["initial"]["panels"][:3], model["second"]["panels"])
        self.assertEqual(hosts(model["first"])[0][1]["id"], hosts(model["second"])[0][1]["id"])

    def test_repeat_keeps_one_global_host_and_its_configuration(self):
        model = run_layout()
        for run in ("first", "second"):
            self.assertIsNone(model[run]["error"])
            self.assertEqual(1, len(hosts(model[run])))
            self.assertEqual(0, hosts(model[run])[0][0]["screen"])
            self.assertEqual("DP-1", hosts(model[run])[0][1]["config"].get("General/primaryConnector"))
        self.assertEqual(hosts(model["beforeSecond"]), hosts(model["second"]))
        self.assertEqual(hosts(model["first"])[0][1]["id"], hosts(model["second"])[0][1]["id"])
        self.assertFalse(model["second"]["events"])

    def test_only_managed_panels_removed_after_host_added(self):
        model = run_layout()
        for run in ("first", "second"):
            self.assertEqual(model["initial"]["panels"][:3], model[run]["panels"])
            self.assertFalse(any(event["action"] == "createPanel" for event in model[run]["events"]))
        actions = [event["action"] for event in model["first"]["events"]]
        self.assertEqual(["addWidget", "removeContainment", "removeContainment"], actions)
        added = [event["type"] for event in model["first"]["events"] if event["action"] == "addWidget"]
        self.assertEqual([LAUNCHER], added)

    def test_preflight_failures_make_no_changes(self):
        scenarios = [
            {"unavailable": True},
            {"desktops": []},
            {"desktops": [{"screen": 1}]},
            {"desktops": [{"screen": 0, "activity": "other"}]},
            {"connectors": {"eDP-1": 1}},
            {"addFailure": "error"},
            {"addFailure": "undefined"},
            {"addFailure": "throw"},
        ]
        for options in scenarios:
            with self.subTest(options=options):
                model = run_layout(**options)
                self.assertIsNotNone(model["first"]["error"])
                for key in ("desktops", "panels"):
                    self.assertEqual(model["initial"][key], model["first"][key])
                self.assertEqual([], model["first"]["events"])

    def test_current_activity_primary_desktop_chosen_without_adding_desktops(self):
        model = run_layout(desktops=[
            {"screen": 0, "activity": "other"},
            {"screen": 1}, {"screen": 0}, {"screen": 2},
        ])
        self.assertIsNone(model["first"]["error"])
        self.assertEqual(4, len(model["first"]["desktops"]))
        self.assertEqual(1, len(hosts(model["first"])))
        self.assertEqual(model["initial"]["desktops"][2]["id"], hosts(model["first"])[0][0]["id"])

    def test_disconnected_internal_connector_does_not_block_launcher(self):
        model = run_layout(connectors={"DP-1": 0}, desktops=[{"screen": 0}])
        self.assertIsNone(model["first"]["error"])
        self.assertEqual(1, len(hosts(model["first"])))

    def test_primary_change_keeps_embedded_host_owner_and_configuration(self):
        for disconnected in (False, True):
            with self.subTest(disconnected=disconnected):
                model = run_layout(movePrimary=True, disconnectOldPrimary=disconnected)
                self.assertIsNone(model["second"]["error"])
                self.assertEqual(1, len(hosts(model["second"])))
                desktop, widget = hosts(model["second"])[0]
                self.assertEqual(-1 if disconnected else 0, desktop["screen"])
                previous = hosts(model["beforeSecond"])[0][1]
                self.assertEqual(previous["id"], widget["id"])
                expected_config = {**previous["config"], "General/primaryConnector": "eDP-1"}
                self.assertEqual(expected_config, widget["config"])
                self.assertEqual([], model["second"]["events"])

    def test_stale_saved_readiness_cannot_remove_panels(self):
        model = run_layout(staleReady=True, desktops=[
            {"screen": 0, "widgets": [{"type": LAUNCHER, "config": {
                "Arasaka/Managed": True, "General/ready": True,
                "General/readyToken": "old-bus/:1.42",
            }}]},
        ])
        self.assertIsNotNone(model["first"]["error"])
        self.assertEqual(model["initial"]["panels"], model["first"]["panels"])

    def test_existing_host_retargets_without_a_primary_desktop(self):
        for connector, screens in (
            ("eDP-1", {"eDP-1": 0}),
            ("HDMI-A-1", {"HDMI-A-1": 0}),
            ("DP-11", {"eDP-1": 0, "DP-11": 1, "DP-10": 2}),
        ):
            for activity in ("current", ""):
                with self.subTest(connector=connector, activity=activity):
                    model = run_layout(primaryConnector=connector, connectors=screens,
                        currentActivity=activity, desktops=[
                            {"screen": -1, "widgets": [{"type": LAUNCHER, "config": {
                                "Arasaka/Managed": True, "General/primaryConnector": "DP-2",
                                "General/nativeIds": "42,43",
                            }}]},
                        ])
                    for run in ("first", "second"):
                        self.assertIsNone(model[run]["error"])
                        desktop, widget = hosts(model[run])[0]
                        self.assertEqual(-1, desktop["screen"])
                        self.assertEqual(hosts(model["initial"])[0][1]["id"], widget["id"])
                        self.assertEqual(connector, widget["config"]["General/primaryConnector"])
                        self.assertEqual("42,43", widget["config"]["General/nativeIds"])
                        self.assertFalse(any(e["action"] in ("addWidget", "moveWidget")
                                             for e in model[run]["events"]))
                    self.assertEqual([], model["second"]["events"])

    def test_stale_managed_hosts_converge_without_touching_unmanaged_widgets(self):
        model = run_layout(desktops=[
            {"screen": 1, "widgets": [{"type": LAUNCHER, "config": {"Arasaka/Managed": "true"}}]},
            {"screen": 0, "widgets": [
                {"type": "example.user.widget", "config": {"General/value": "keep"}},
                {"type": LAUNCHER, "config": {"Arasaka/Managed": False}},
                {"type": LAUNCHER, "config": {"Arasaka/Managed": True, "General/nativeIds": "42,43"}},
            ]},
        ])
        self.assertIsNone(model["first"]["error"])
        self.assertEqual(1, len(hosts(model["first"])))
        self.assertEqual(model["initial"]["desktops"][1]["widgets"][2]["id"], hosts(model["first"])[0][1]["id"])
        self.assertEqual("42,43", hosts(model["first"])[0][1]["config"]["General/nativeIds"])
        self.assertEqual(model["initial"]["desktops"][1]["widgets"][:2], model["first"]["desktops"][1]["widgets"][:2])

    def test_launcher_only_preserves_wallpaper_and_desktop_settings(self):
        model = run_layout(desktops=[{"screen": 0,
            "wallpaperPlugin": "example.user.wallpaper",
            "config": {"General/filterMode": 0, "Wallpaper/example.user.wallpaper/General/value": "keep"},
        }])
        self.assertIsNone(model["first"]["error"])
        self.assertEqual(model["initial"]["desktops"][0]["config"], model["first"]["desktops"][0]["config"])
        self.assertEqual("example.user.wallpaper", model["first"]["desktops"][0]["wallpaperPlugin"])

    def test_full_theme_icon_policy_preserves_wallpapers(self):
        model = run_layout(hideDesktopIcons=True)
        self.assertIsNone(model["first"]["error"])
        for desktop in model["first"]["desktops"]:
            self.assertEqual("org.kde.image", desktop["wallpaperPlugin"])
            config = desktop["config"]
            self.assertEqual(1, config["General/filterMode"])
            self.assertEqual("__ARASAKA_DESKTOP_ITEMS_HIDDEN__", config["General/filterPattern"])


if __name__ == "__main__":
    unittest.main()
