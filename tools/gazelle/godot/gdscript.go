// Sections: Lexer, Script scan.

package godot

import (
	"slices"
	"strings"
	"unicode"
)

// ==== Lexer ===================================================================

// The kinds of a GDScript token.
const (
	identifier  = 'i'
	stringToken = 's'
	punctuation = 'p'
)

// A token of GDScript: an identifier, a string literal with its contents unescaped, or a
// punctuation character.
type token struct {
	kind byte
	text string
}

// A lexer splits GDScript into tokens, leaving out comments, whitespace and numbers.
type lexer struct {
	source string
	i      int
	tokens []token
}

func lexScript(source string) []token {
	l := &lexer{source: source}
	for l.i < len(source) {
		l.step()
	}
	return l.tokens
}

// step reads what starts at the lexer's position.
func (l *lexer) step() {
	c := l.source[l.i]
	switch {
	case c == '#':
		l.skipWhile(func(c byte) bool { return c != '\n' })
	case isQuote(c):
		l.readString(false)
	case isWordStart(c):
		l.readWord()
	case isDigit(c):
		l.skipWhile(isNumberPart)
	case strings.IndexByte(" \t\r\n", c) >= 0:
		l.i++
	default:
		// The & of a StringName and the ^ of a NodePath literal stay punctuation.
		l.tokens = append(l.tokens, token{punctuation, string(c)})
		l.i++
	}
}

func (l *lexer) quoteFollows() bool {
	return l.i < len(l.source) && isQuote(l.source[l.i])
}

func (l *lexer) skipWhile(keep func(byte) bool) {
	for l.i < len(l.source) && keep(l.source[l.i]) {
		l.i++
	}
}

// readWord reads an identifier, or the raw string that an r before a quote starts.
func (l *lexer) readWord() {
	start := l.i
	l.skipWhile(isWordPart)
	word := l.source[start:l.i]
	if word == "r" && l.quoteFollows() {
		l.readString(true)
		return
	}
	l.tokens = append(l.tokens, token{identifier, word})
}

// readString reads the string literal that starts with the quote at the lexer's position,
// single or triple.
func (l *lexer) readString(raw bool) {
	quote := l.source[l.i : l.i+1]
	if strings.HasPrefix(l.source[l.i:], strings.Repeat(quote, 3)) {
		quote = strings.Repeat(quote, 3)
	}
	l.i += len(quote)
	var text strings.Builder
	for l.i < len(l.source) && !strings.HasPrefix(l.source[l.i:], quote) {
		if !raw && l.escapes() {
			l.i++
		}
		text.WriteByte(l.source[l.i])
		l.i++
	}
	l.i += len(quote)
	l.tokens = append(l.tokens, token{stringToken, text.String()})
}

// escapes reports whether a backslash at the lexer's position escapes the next character.
func (l *lexer) escapes() bool {
	return l.source[l.i] == '\\' && l.i+1 < len(l.source)
}

func isQuote(c byte) bool     { return c == '"' || c == '\'' }
func isDigit(c byte) bool     { return unicode.IsDigit(rune(c)) }
func isWordStart(c byte) bool { return c == '_' || unicode.IsLetter(rune(c)) }
func isWordPart(c byte) bool  { return isWordStart(c) || isDigit(c) }

// isNumberPart covers digits, separators, exponents, hexadecimal digits and suffixes alike.
func isNumberPart(c byte) bool { return isWordPart(c) || c == '.' }

// ==== Script scan =============================================================

// Keywords whose next identifier a script declares itself, so that it names no global class.
var declaringKeywords = map[string]bool{
	"class": true, "class_name": true, "const": true, "enum": true, "func": true,
	"signal": true, "var": true,
}

// A scriptScan collects what a script declares and references, token by token.
type scriptScan struct {
	scanned
	resPath string
	tokens  []token
	// The names the script declares itself, and the capitalized names it uses.
	local   map[string]bool
	used    []string
	// Whether the tokens are inside the braces of an enum, whose identifiers are its values.
	inEnum bool
}

// scanScript reads a GDScript file: its class_name, its extends, the paths of its literal
// load and preload calls, the res:// paths of its other literals and every capitalized
// identifier that may name a global class. Comments and string contents name nothing.
func scanScript(resPath string, content []byte) scanned {
	s := &scriptScan{resPath: resPath, tokens: lexScript(string(content)), local: map[string]bool{}}
	for i, t := range s.tokens {
		s.visit(i, t)
	}
	s.addClassReferences()
	return s.scanned
}

func (s *scriptScan) visit(i int, t token) {
	switch t.kind {
	case stringToken:
		s.visitString(i, t.text)
	case identifier:
		if !s.visitDeclaration(i, t.text) {
			s.visitUse(i, t.text)
		}
	case punctuation:
		s.inEnum = s.inEnum && t.text != "}"
	}
}

// addClassReferences references the capitalized names the script uses but does not declare.
func (s *scriptScan) addClassReferences() {
	for _, name := range s.used {
		if !s.local[name] && !slices.Contains(s.classes, name) {
			s.refs = append(s.refs, reference{kindClass, name})
		}
	}
}

// before returns the token n places before the one at i, or none.
func (s *scriptScan) before(i, n int) token {
	if i < n {
		return token{}
	}
	return s.tokens[i-n]
}

func (s *scriptScan) visitString(i int, text string) {
	switch call := s.before(i, 2); {
	case s.before(i, 1).text == "(" && call.kind == identifier && (call.text == "load" || call.text == "preload"):
		s.addPath(text, s.resPath)
	case s.before(i, 1).text == "extends":
		s.extends, _ = resourcePath(text, s.resPath)
		s.addPath(text, s.resPath)
	case strings.HasPrefix(text, "res://"):
		if resolved, ok := resourcePath(text, s.resPath); ok {
			s.literals = append(s.literals, resolved)
		}
	}
}

// visitDeclaration records an identifier the script declares, and reports whether it was one.
func (s *scriptScan) visitDeclaration(i int, text string) bool {
	previous := s.before(i, 1)
	switch {
	case text == "enum":
		s.inEnum = true
	case previous.text == "class_name":
		s.classes = append(s.classes, text)
	case s.inEnum || previous.kind == identifier && declaringKeywords[previous.text]:
		s.local[text] = true
	default:
		return false
	}
	return true
}

// visitUse records an identifier that may name a global class.
func (s *scriptScan) visitUse(i int, text string) {
	previous := s.before(i, 1)
	switch {
	case previous.text == "extends":
		s.extends = text
		s.used = append(s.used, text)
	case previous.kind == punctuation && strings.Contains(".$%@", previous.text):
		// A member, a node path or an annotation.
	case unicode.IsUpper(rune(text[0])):
		s.used = append(s.used, text)
	}
}
