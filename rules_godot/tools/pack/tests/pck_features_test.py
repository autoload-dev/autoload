"""Simulator CPU synthesis must not lie about the runtime's actual CPU features."""

import struct
import tempfile
import unittest
from pathlib import Path

from tools.pack import pck


def record(name: str, value: bytes) -> bytes:
    key = name.encode()
    return struct.pack("<I", len(key)) + key + struct.pack("<I", len(value)) + value


def string(value: str) -> bytes:
    data = value.encode()
    return struct.pack("<II", 4, len(data)) + data + bytes(-len(data) % 4)


def config(*records: bytes) -> bytes:
    return b"ECFG" + struct.pack("<I", len(records)) + b"".join(records)


class PackedFeaturesTest(unittest.TestCase):
    def test_pack_rewrite_changes_only_project_features(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty, exported, final = (
                root / name for name in ["empty.pck", "exported.pck", "final.pck"]
            )
            empty.write_bytes(
                struct.pack("<6IQQI", 0x43504447, 4, 4, 7, 2, 0, 0, 40, 0) + bytes(128)
            )
            before = config(record("_custom_features", string("game,simulator,x86_64")))
            pck.add_pck_files(
                empty,
                exported,
                {
                    "project.binary": before,
                    "native/extension.gdextension": b"descriptor",
                    "asset.txt": b"asset",
                },
            )
            # The pack action's rewrite of the exported settings.
            pck.add_pck_files(
                exported,
                final,
                {
                    "project.binary": pck.normalize_project_features(
                        pck.pck_file_member(exported, "project.binary"), {"x86_64"}
                    )
                },
            )
            with final.open("rb") as source:
                _, entries = pck._directory(source, final.stat().st_size)
                values = {}
                for entry in entries:
                    source.seek(entry.offset)
                    values[entry.path] = source.read(entry.size)
            self.assertEqual(
                config(record("_custom_features", string("game,simulator"))),
                values.pop("project.binary"),
            )
            self.assertEqual(
                {"native/extension.gdextension": b"descriptor", "asset.txt": b"asset"},
                values,
            )
            self.assertEqual(b"asset", pck.pck_member(final.read_bytes(), "asset.txt"))
            self.assertEqual(
                {"game", "simulator"},
                pck.project_features(
                    pck.pck_member(final.read_bytes(), "res://project.binary")
                ),
            )
            self.assertEqual(set(), pck.project_features(config()))

    def test_setting_keys_include_feature_overrides(self) -> None:
        packed = config(
            record("application/config/description", string("device")),
            record("application/config/description.simulator", string("simulator")),
        )
        self.assertEqual(
            {
                "application/config/description",
                "application/config/description.simulator",
            },
            pck.project_setting_keys(packed),
        )

    def normalize(self, data: bytes, synthesized: set[str]) -> bytes:
        return pck.normalize_project_features(data, synthesized)

    def test_only_synthesized_cpu_tags_are_removed(self) -> None:
        opaque = record("future/property", b"\x99\x01\x02\x03")
        before = config(
            record("_custom_features", string("game_tag,simulator,arm64,x86_64")), opaque
        )
        after = config(record("_custom_features", string("game_tag,simulator")), opaque)
        self.assertEqual(after, self.normalize(before, {"arm64", "x86_64"}))

    def test_plugin_cpu_occurrence_survives_synthetic_removal(self) -> None:
        before = config(
            record("_custom_features", string("telemetry,simulator,x86_64,x86_64"))
        )
        after = config(record("_custom_features", string("telemetry,simulator,x86_64")))
        self.assertEqual(after, self.normalize(before, {"x86_64"}))

    def test_empty_synthesis_preserves_bytes(self) -> None:
        data = config(record("_custom_features", string("game_tag,simulator")))
        self.assertEqual(data, self.normalize(data, set()))

    def test_empty_custom_features_record_is_removed(self) -> None:
        self.assertEqual(
            config(),
            self.normalize(
                config(record("_custom_features", string("arm64"))), {"arm64"}
            ),
        )

    def test_synthesized_tags_must_exist(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing|absent"):
            self.normalize(
                config(record("_custom_features", string("game_tag"))), {"x86_64"}
            )

    def test_malformed_or_unknown_encoding_is_rejected(self) -> None:
        valid = config(record("_custom_features", string("arm64")))
        for malformed in [
            b"bad",
            b"????" + valid[4:],
            valid[:-1],
            valid + b"trailing",
            config(record("_custom_features", struct.pack("<I", 5))),
            config(
                record("_custom_features", string("arm64")),
                record("_custom_features", string("arm64")),
            ),
        ]:
            with self.subTest(data=malformed), self.assertRaises(ValueError):
                self.normalize(malformed, {"arm64"})

    def test_only_cpu_tags_can_be_synthesized(self) -> None:
        with self.assertRaisesRegex(ValueError, "CPU|cpu"):
            self.normalize(
                config(record("_custom_features", string("game_tag"))), {"game_tag"}
            )


if __name__ == "__main__":
    unittest.main()
