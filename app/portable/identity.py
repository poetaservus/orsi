"""Installation identity is independent of the selected personal profile."""
from pathlib import Path


NODE_MANIFEST = "NODE_MANIFEST.json"
DEPLOYMENT_DISABLED = "Portable nodes cannot deploy other nodes. Use the local O.R.S.I app."


def is_deployed_node(root):
    # Recognize existing exports and the earlier pilot, even with a damaged manifest.
    return any((Path(root) / name).exists() or (Path(root) / name).is_symlink()
               for name in (NODE_MANIFEST, "PACKAGE_MANIFEST.json"))


def node_name(number):
    return f"O.R.S.I Portable Node Nr. {number:03d}"
