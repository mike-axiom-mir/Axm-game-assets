import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / ".axm" / "beacon" / "beacon.py"
spec = importlib.util.spec_from_file_location("asset_forge_beacon", MODULE_PATH)
beacon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = beacon
assert spec.loader is not None
spec.loader.exec_module(beacon)
network = sys.modules["network"]

REFERENCE_CAPSULE_ID = "2345cdcd6107af8a453480e50b2e598c91ac63f4440179ef459f78418f474e8d"


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, check=True, text=True, stdout=subprocess.PIPE)
    return proc.stdout.strip()


class _Response:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.content


class AssetForgeBeaconTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="asset-forge-beacon-"))
        git(root, "init", "-q")
        git(root, "config", "user.email", "beacon-test@example.invalid")
        git(root, "config", "user.name", "Beacon Test")
        (root / ".axm").mkdir()
        shutil.copy2(ROOT / ".axm" / "beacon.json", root / ".axm" / "beacon.json")
        (root / "README.md").write_text("asset forge fixture\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "seed asset forge fixture")
        return root

    def add_asset_domain_change(self, root: Path) -> tuple[str, str]:
        base = git(root, "rev-parse", "HEAD")
        (root / "docs").mkdir()
        (root / "native_material_repair.py").write_text(
            "def repair_pbr_material(surface_state):\n"
            "    return {**surface_state, 'receipt': 'pbr-repair'}\n",
            encoding="utf-8",
        )
        (root / "native_material_repair_test.py").write_text(
            "from native_material_repair import repair_pbr_material\n",
            encoding="utf-8",
        )
        (root / "docs" / "PBR_MATERIAL_REPAIR.md").write_text(
            "# PBR material repair evidence\n",
            encoding="utf-8",
        )
        git(root, "add", ".")
        git(root, "commit", "-qm", "add deterministic PBR material repair receipt")
        return base, git(root, "rev-parse", "HEAD")

    def test_real_asset_change_publishes_reproducibly_and_surfaces_domain_signal(self):
        root = self.make_repo()
        base, head = self.add_asset_domain_change(root)
        first = beacon.publish(root, base, head, root / "feed-a", ".axm/beacon.json")
        second = beacon.publish(root, base, head, root / "feed-b", ".axm/beacon.json")
        self.assertEqual(first["capsule_id"], second["capsule_id"])
        self.assertEqual(first["evidence"]["patch_sha256"], second["evidence"]["patch_sha256"])
        self.assertFalse(first["transfer"]["auto_apply"])
        material = next(item for item in first["evidence"]["files"] if item["path"] == "native_material_repair.py")
        self.assertIn("repair_pbr_material", material["symbols"])
        self.assertTrue({"material", "pbr", "repair"}.issubset(first["signals"]["tags"]))
        self.assertIn("test-change", first["signals"]["kinds"])
        self.assertEqual(beacon.verify_capsule(first), (True, "ok"))

    def test_quarantined_private_and_seed_content_cannot_enter_capsule_or_patch(self):
        root = self.make_repo()
        base = git(root, "rev-parse", "HEAD")
        (root / "native_vfx.py").write_text("def bounded_vfx_receipt():\n    return 'safe'\n", encoding="utf-8")
        forbidden = {
            "seed_data/quarantined/model.bin": "QUARANTINED-ASSET-BYTES",
            "private/artist-note.txt": "PRIVATE-ASSET-NOTE",
            ".env.local": "GITHUB_TOKEN=DO-NOT-LEAK",
            "build/export/credential.pem": "NON-EXPORTABLE-CREDENTIAL",
        }
        for relative, content in forbidden.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "add safe VFX receipt beside excluded state")
        capsule = beacon.publish(root, base, "HEAD", root / "feed", ".axm/beacon.json")
        paths = {item["path"] for item in capsule["evidence"]["files"]}
        self.assertEqual(paths, {"native_vfx.py"})
        patch = (root / "feed" / "patches" / f"{capsule['capsule_id']}.patch").read_text(encoding="utf-8")
        self.assertIn("bounded_vfx_receipt", patch)
        for relative, content in forbidden.items():
            self.assertNotIn(relative, patch)
            self.assertNotIn(content, patch)

    def test_receiver_ranks_the_exact_discovery_buddy_reference_capsule(self):
        fixture = json.loads((ROOT / "tests" / "fixtures" / "axm_beacon_reference_index.json").read_text(encoding="utf-8"))
        config = beacon.load_config(ROOT, ".axm/beacon.json")
        ranked = network.rank_candidates([fixture], config["repo"], config["interests"])
        self.assertEqual(ranked[0]["capsule_id"], REFERENCE_CAPSULE_ID)
        self.assertGreater(ranked[0]["relevance_score"], ranked[0]["attention_score"])
        self.assertTrue({"canonical", "identity", "organ", "protocol"}.intersection(ranked[0]["interest_overlap"]))

    def test_fetch_writes_only_a_proposal_inbox_and_never_mutates_canonical_state(self):
        root = self.make_repo()
        base, head = self.add_asset_domain_change(root)
        capsule = beacon.publish(root, base, head, root / "source-feed", ".axm/beacon.json")
        patch = (root / "source-feed" / "patches" / f"{capsule['capsule_id']}.patch").read_bytes()
        canonical = root / "asset_genome.json"
        canonical.write_text("canonical-state-unchanged\n", encoding="utf-8")
        inbox = root / ".axm" / "beacon" / "inbox"
        with mock.patch.object(network, "_request_json", return_value=capsule), mock.patch.object(network.urllib.request, "urlopen", return_value=_Response(patch)):
            capsule_path, patch_path = network.fetch_capsule("example/source", capsule["capsule_id"], "axm-beacon-feed", inbox)
        self.assertEqual(canonical.read_text(encoding="utf-8"), "canonical-state-unchanged\n")
        self.assertTrue(capsule_path.is_relative_to(inbox))
        self.assertTrue(patch_path.is_relative_to(inbox))
        self.assertEqual((capsule_path.parent / "STATUS.txt").read_text(encoding="utf-8").splitlines()[:2], ["proposal-only", "not applied"])

    def test_tampered_capsule_and_patch_are_rejected(self):
        root = self.make_repo()
        base, head = self.add_asset_domain_change(root)
        capsule = beacon.publish(root, base, head, root / "source-feed", ".axm/beacon.json")
        altered = json.loads(json.dumps(capsule))
        altered["signals"]["attention_score"] += 1
        self.assertFalse(beacon.verify_capsule(altered)[0])
        with mock.patch.object(network, "_request_json", return_value=capsule), mock.patch.object(network.urllib.request, "urlopen", return_value=_Response(b"altered patch")):
            with self.assertRaises(beacon.BeaconError):
                network.fetch_capsule("example/source", capsule["capsule_id"], "axm-beacon-feed", root / "inbox")


if __name__ == "__main__":
    unittest.main()
