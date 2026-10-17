"""Export every installed third-party version for a strict, resolver-free audit."""

import argparse
import importlib.metadata
import json
import re
from pathlib import Path


def export_packages(packages):
    versions = {}
    for package in packages:
        name = package["name"].lower().replace("_", "-")
        version = package["version"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", name) or not re.fullmatch(
            r"[A-Za-z0-9.+!-]+", version
        ):
            raise ValueError("Unsafe package metadata")
        if name in versions and versions[name] != version:
            raise ValueError(f"Conflicting installed versions: {name}")
        versions[name] = version
    if versions.pop("model-atlas-backend", None) != "1.0.0":
        raise ValueError("Expected the installed first-party application version 1.0.0")
    if not {"pip", "fastapi", "pyjwt", "cryptography", "pypdf", "anyio"} <= versions.keys():
        raise ValueError("Incomplete backend dependency inventory")
    return "".join(f"{name}=={version}\n" for name, version in sorted(versions.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, help="JSON from python -m pip list --format=json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packages = (
        json.loads(args.inventory.read_text(encoding="utf-8-sig"))
        if args.inventory
        else [
            {"name": item.metadata["Name"], "version": item.version}
            for item in importlib.metadata.distributions()
        ]
    )
    text = export_packages(packages)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(text)
    print(
        json.dumps(
            {
                "audited_third_party_packages": len(text.splitlines()),
                "excluded_first_party_only": "model-atlas-backend==1.0.0",
            }
        )
    )


if __name__ == "__main__":
    main()
