"""Check profile structure and selector matches without clicking."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from run_app import ROOT, Scenario, validate_profile, NeedsConfiguration, bounds


class XmlDevice:
    def __init__(self, xml, package):
        self.xml, self.package = xml, package
        nodes = list(ET.fromstring(xml).iter("node"))
        self.size = (max((bounds(n.get("bounds", ""))[2] for n in nodes), default=1260),
                     max((bounds(n.get("bounds", ""))[3] for n in nodes), default=2844))

    def window_size(self):
        return self.size

    def app_current(self):
        return {"package": self.package}

    def dump_hierarchy(self):
        return self.xml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--xml", type=Path)
    parser.add_argument("--step")
    args = parser.parse_args()
    profile = json.loads((ROOT / "profiles" / (args.app + ".json")).read_text(encoding="utf-8"))
    try:
        validate_profile(profile)
    except NeedsConfiguration as exc:
        print("NEEDS_CONFIGURATION:", exc)
        if not args.xml:
            return 3
    if not args.xml:
        print("Structure valid. Actual UI selectors remain UNVERIFIED_ON_DEVICE.")
        return 0
    xml = args.xml.read_text(encoding="utf-8")
    scenario = Scenario(XmlDevice(xml, profile["package"]), profile, Path("."))
    tree = ET.fromstring(xml)
    if args.step:
        step = next(s for s in profile["steps"] if s["name"] == args.step)
        for selector in step.get("selectors", []):
            found = scenario.candidates(tree, selector)
            print(json.dumps({"selector": selector, "matches": len(found),
                              "targets": [n.attrib for n in found]}, ensure_ascii=False, indent=2))
    else:
        counts = [[len(scenario.candidates(tree, s)) for s in g] for g in profile["home"]]
        print("Home selector group matches:", counts)
        if not all(any(c > 0 for c in g) for g in counts):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
