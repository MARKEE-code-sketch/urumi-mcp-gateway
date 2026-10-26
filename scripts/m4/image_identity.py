"""Verify a Docker save archive's actual runtime config; never trust tag alone."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with tarfile.open(args.archive) as archive:
        manifests = json.load(archive.extractfile("manifest.json"))
        matching = [item for item in manifests if args.image in item.get("RepoTags", [])]
        if len(matching) != 1:
            raise SystemExit("Exactly one exported requested image is required.")
        config_path = matching[0]["Config"]
        config = archive.extractfile(config_path).read()
        digest = hashlib.sha256(config).hexdigest()
        if digest not in config_path:
            raise SystemExit("Exported config path and actual hash disagree.")
        runtime = json.loads(config)
        evidence = {"image": args.image, "config_digest": "sha256:" + digest,
                    "architecture": runtime["architecture"], "os": runtime["os"],
                    "verification": "SHA256 of actual Docker-exported configuration bytes"}
    Path(args.output).write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
