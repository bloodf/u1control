"""Write tests/fixtures/orca_generic_ids.json: the filament_id of every "Generic <family> @System" preset in
OrcaSlicer's OrcaFilamentLibrary at one commit, resolved through "inherits". tests check the GENERIC_IDS table
against it. Refresh with a new commit when OrcaSlicer's library changes:

    python scripts/generic_ids.py /path/to/OrcaSlicer <commit> > tests/fixtures/orca_generic_ids.json
"""

import json
import subprocess
import sys

LIBRARY = "resources/profiles/OrcaFilamentLibrary/filament"


def main(repo, commit):
    commit = subprocess.check_output(["git", "-C", repo, "rev-parse", commit], text=True).strip()
    paths = subprocess.check_output(["git", "-C", repo, "ls-tree", "-r", "-z", "--name-only", commit, LIBRARY],
                                    text=True).split("\0")
    presets = {}
    for path in (p for p in paths if p.endswith(".json")):
        data = json.loads(subprocess.check_output(["git", "-C", repo, "show", "%s:%s" % (commit, path)], text=True))
        presets[data.get("name")] = data

    def filament_id(name, depth=0):
        data = presets.get(name) or {}
        return data.get("filament_id") or (filament_id(data.get("inherits"), depth + 1) if depth < 10 else None)

    ids = {name[len("Generic "):-len(" @System")]: filament_id(name) for name in sorted(presets)
           if name.startswith("Generic ") and name.endswith(" @System")}
    json.dump({"commit": commit, "ids": ids}, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
