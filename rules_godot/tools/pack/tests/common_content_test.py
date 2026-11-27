"""A shared PCK requires a conflict-free union of its platform slices' descriptors."""

import unittest

from tools.pack import common_content


class CommonContentTest(unittest.TestCase):
    def test_union_preserves_configuration_and_every_platform_slice(self) -> None:
        descriptor = '[configuration]\nentry_symbol="example_init"\n[libraries]\n'
        merged = common_content.merge_descriptors(
            [
                ("arm64", descriptor + 'ios.arm64="res://arm64.a"\n'),
                ("x86_64", descriptor + 'ios.x86_64="res://x86_64.a"\n'),
            ]
        )
        self.assertIn('entry_symbol="example_init"', merged)
        self.assertIn('ios.arm64="res://arm64.a"', merged)
        self.assertIn('ios.x86_64="res://x86_64.a"', merged)
        self.assertEqual(1, merged.count("[configuration]"))

    def test_union_rejects_mismatched_configuration_or_same_feature(self) -> None:
        for other in [
            '[configuration]\nentry_symbol="another_init"\n[libraries]\nios.arm64="res://arm64.a"\n',
            '[configuration]\nentry_symbol="example_init"\n[libraries]\nios.arm64="res://different.a"\n',
        ]:
            with (
                self.subTest(other=other),
                self.assertRaisesRegex(ValueError, "Descriptor"),
            ):
                common_content.merge_descriptors(
                    [
                        (
                            "arm64",
                            '[configuration]\nentry_symbol="example_init"\n[libraries]\nios.arm64="res://arm64.a"\n',
                        ),
                        ("x86_64", other),
                    ]
                )

    def test_a_descriptor_needs_sectioned_unique_keys(self) -> None:
        for text, message in [
            ('entry_symbol="example_init"\n', "arm64 has an unsectioned key"),
            (
                '[configuration]\nentry_symbol="a"\nentry_symbol="b"\n',
                r"arm64 repeats \('configuration', 'entry_symbol'\)",
            ),
        ]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, message):
                common_content.merge_descriptors([("arm64", text)])

    def test_the_union_is_sorted_by_section_and_key(self) -> None:
        merged = common_content.merge_descriptors(
            [("arm64", '[libraries]\nz="z"\na="a"\n[configuration]\nentry_symbol="e"\n')]
        )
        self.assertEqual(
            '[configuration]\nentry_symbol="e"\n\n[libraries]\na="a"\nz="z"\n', merged
        )
