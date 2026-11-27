"""The text of Godot resources as the build tools read it."""

import unittest

from tools.resource_text import lex


class LexerTest(unittest.TestCase):
    def test_the_lexer_decodes_escapes_but_keeps_raw_strings_verbatim(self) -> None:
        text = "'a\\nb\\u00e9\\q' r'x\\ny' \"open"
        self.assertEqual(
            [("string", "a\nbé\\q"), ("string", "x\\ny"), ("invalid", "open")],
            [(token.category, token.value) for token in lex(text)],
        )


if __name__ == "__main__":
    unittest.main()
