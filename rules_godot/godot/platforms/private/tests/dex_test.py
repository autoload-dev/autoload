import struct
import unittest

from godot.platforms.private.tests.dex import defined_classes


def dex_file(descriptor: bytes, version: bytes = b"035", string_index: int = 0) -> bytes:
    """Return a DEX file whose one class has the type descriptor."""
    strings, types, classes, data = 112, 116, 120, 152
    string = bytes([len(descriptor)]) + descriptor + b"\0"
    size = data + len(string)
    header = bytearray(112)
    header[:8] = b"dex\n" + version + b"\0"
    struct.pack_into("<III", header, 32, size, 112, 0x12345678)
    struct.pack_into("<II", header, 56, 1, strings)
    struct.pack_into("<II", header, 64, 1, types)
    struct.pack_into("<II", header, 96, 1, classes)
    return (
        bytes(header)
        + struct.pack("<I", data)
        + struct.pack("<I", string_index)
        + struct.pack("<I", 0)
        + bytes(28)
        + string
    )


class DexTest(unittest.TestCase):
    def test_defined_classes_name_each_class_definition(self) -> None:
        self.assertEqual(
            defined_classes(dex_file(b"Lorg/example/Hello;")), {"org.example.Hello"}
        )

    def test_unsupported_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported DEX version"):
            defined_classes(dex_file(b"Lorg/example/Hello;", version=b"034"))

    def test_descriptor_outside_string_table_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside string table"):
            defined_classes(dex_file(b"Lorg/example/Hello;", string_index=1))

    def test_type_that_is_no_class_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid DEX class descriptor"):
            defined_classes(dex_file(b"I"))


if __name__ == "__main__":
    unittest.main()
