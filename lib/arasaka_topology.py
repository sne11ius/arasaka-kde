import json
import re
import sys


class NoEnabledOutputs(ValueError):
    pass


def classify_output(connector: str) -> str:
    if re.match(r"^(?:eDP|LVDS|DSI)(?:-|$)", connector):
        return "internal"
    return "external"


def choose_primary(outputs: list[dict]) -> str:
    def priority_key(output):
        priority = output.get("priority") or 2**31
        return (priority, output["name"])

    enabled = [
        output
        for output in outputs
        if output.get("connected", False) and output.get("enabled", False)
    ]
    external = [
        output for output in enabled if classify_output(output["name"]) == "external"
    ]
    if not enabled:
        raise NoEnabledOutputs("topology has no connected, enabled outputs")
    return min(external or enabled, key=priority_key)["name"]


def priority_changes(outputs: list[dict]) -> list[tuple[str, int]]:
    primary = choose_primary(outputs)
    current = next(output for output in outputs if output["name"] == primary)
    if current.get("priority") == 1:
        return []
    return [(primary, 1)]


def topology_signature(outputs: list[dict]) -> str:
    enabled = [
        output
        for output in outputs
        if output.get("connected", False) and output.get("enabled", False)
    ]
    primary = choose_primary(enabled)
    internal = next(
        (output["name"] for output in enabled if classify_output(output["name"]) == "internal"),
        None,
    )
    return json.dumps(
        {
            "enabled": sorted(output["name"] for output in enabled),
            "internal": internal,
            "primary": primary,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def build_plan(topology: dict) -> dict:
    outputs = [
        output
        for output in topology["outputs"]
        if output.get("connected", False) and output.get("enabled", False)
    ]
    primary = choose_primary(outputs)
    internal = next(
        (output["name"] for output in outputs if classify_output(output["name"]) == "internal"),
        None,
    )
    return {
        "primary": primary,
        "internal": internal,
        "changes": priority_changes(outputs),
        "signature": topology_signature(outputs),
    }


def main() -> int:
    topology = json.load(sys.stdin)
    try:
        result = build_plan(topology)
    except NoEnabledOutputs:
        result = {"status": "no-enabled-outputs"}
    json.dump(result, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
