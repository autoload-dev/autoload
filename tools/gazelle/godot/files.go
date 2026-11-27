// Sections: Formats, Package files, Names.

package godot

import (
	"os"
	"path"
	"path/filepath"
	"slices"
	"strings"
	"unicode"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/pathtools"
)

// ==== Formats =================================================================

// The sidecars Godot writes beside a file: its import settings and its UID, as the ruleset's
// build tools know them (rules_godot/tools/godot_files.py).
var sidecarSuffixes = []string{".import", ".uid"}

// Formats whose files are resources by their suffix; a file of any other format is one when
// it has a sidecar, such as a script of another language with its .uid, or a file of its
// package names its res:// path.
var (
	importableFormats = suffixes(".bmp", ".dds", ".exr", ".fbx", ".glb", ".gltf", ".hdr",
		".jpeg", ".jpg", ".ktx", ".mp3", ".obj", ".ogg", ".otf", ".png", ".svg", ".tga",
		".ttf", ".wav", ".webp", ".woff", ".woff2")
	resourceFormats = suffixes(".gd", ".gdextension", ".gdshader", ".gdshaderinc", ".mo",
		".po", ".res", ".scn", ".shader", ".shaderinc", ".translation", ".tres", ".tscn")
)

func suffixes(values ...string) map[string]bool {
	set := map[string]bool{}
	for _, value := range values {
		set[value] = true
	}
	return set
}

func format(name string) string { return strings.ToLower(path.Ext(name)) }

// sidecarSource returns the file whose sidecar name is, or "" for a name of no sidecar.
func sidecarSource(name string) string {
	for _, suffix := range sidecarSuffixes {
		if strings.HasSuffix(strings.ToLower(name), suffix) && len(name) > len(suffix) {
			return name[:len(name)-len(suffix)]
		}
	}
	return ""
}

// ==== Package files ===========================================================

// directoryFiles returns the files of a directory that Godot sees, with those of its
// subdirectories that are no packages, relative to it.
func (l *godotLang) directoryFiles(args language.GenerateArgs) []string {
	var files []string
	for _, name := range args.RegularFiles {
		if isSourceOfGodot(args.Config, name) {
			files = append(files, name)
		}
	}
	files = append(files, l.pendingFiles(args)...)
	slices.Sort(files)
	return files
}

// pendingFiles returns the files of the subdirectories that are no packages.
func (l *godotLang) pendingFiles(args language.GenerateArgs) []string {
	var files []string
	for _, sub := range args.Subdirs {
		for _, name := range l.pending[path.Join(args.Rel, sub)] {
			files = append(files, path.Join(sub, name))
		}
	}
	return files
}

// isSourceOfGodot reports whether a file of a directory may be a resource: it is visible to
// Godot and neither the project's configuration nor a BUILD file.
func isSourceOfGodot(c *config.Config, name string) bool {
	return !strings.HasPrefix(name, ".") && name != projectFile && !slices.Contains(c.ValidBuildFileNames, name)
}

// scanFile returns what scan finds in a file of the repository, which it reads once, and
// only when scan reads its format.
func (l *godotLang) scanFile(c *config.Config, rel, resPath string) scanned {
	if !scannable(rel) {
		return scanned{}
	}
	name := filepath.Join(c.RepoRoot, filepath.FromSlash(rel))
	if s, ok := l.scans[name]; ok {
		return s
	}
	// A file that cannot be read references nothing.
	content, _ := os.ReadFile(name)
	s := scan(resPath, content)
	l.scans[name] = s
	return s
}

// A package's files and what scan found in each.
type packageFiles struct {
	args    language.GenerateArgs
	project *project
	// The package's directory relative to its project's.
	prefix string
	// The package's files that Godot sees, relative to it, with what scan found in each.
	scans map[string]scanned
}

func (l *godotLang) newPackageFiles(args language.GenerateArgs, p *project, files []string) *packageFiles {
	pf := &packageFiles{
		args:    args,
		project: p,
		prefix:  pathtools.TrimPrefix(args.Rel, p.rel),
		scans:   map[string]scanned{},
	}
	for _, name := range files {
		pf.scans[name] = l.scanFile(args.Config, path.Join(args.Rel, name), pf.resPath(name))
	}
	return pf
}

// has reports whether the package holds a file that Godot sees.
func (p *packageFiles) has(name string) bool {
	_, ok := p.scans[name]
	return ok
}

// resPath returns the res:// path of a file of the package.
func (p *packageFiles) resPath(name string) string {
	return "res://" + path.Join(p.prefix, name)
}

// fileOf returns the file of the package at a res:// path.
func (p *packageFiles) fileOf(resPath string) (string, bool) {
	name := strings.TrimPrefix(resPath, "res://")
	if p.prefix != "" {
		var ok bool
		if name, ok = strings.CutPrefix(name, p.prefix+"/"); !ok {
			return "", false
		}
	}
	return name, p.has(name)
}

// sidecars returns the sidecars of a file that the package holds.
func (p *packageFiles) sidecars(name string) []string {
	var found []string
	for _, suffix := range sidecarSuffixes {
		if p.has(name + suffix) {
			found = append(found, name+suffix)
		}
	}
	return found
}

// isSidecar reports whether a file is the sidecar of another file of the package.
func (p *packageFiles) isSidecar(name string) bool {
	source := sidecarSource(name)
	return source != "" && p.has(source)
}

func (p *packageFiles) isAsset(name string) bool {
	return importableFormats[format(name)] || p.has(name+".import")
}

func (p *packageFiles) isSuite(name string) bool {
	return p.scans[name].extends == suiteBaseClass
}

// members returns the package's resources: the files of resource formats, those with a
// sidecar and those whose res:// paths a file of the package names.
func (p *packageFiles) members() []string {
	named := p.namedPaths()
	var members []string
	for name := range p.scans {
		if !p.isSidecar(name) && p.isResource(name, named) {
			members = append(members, name)
		}
	}
	slices.Sort(members)
	return members
}

func (p *packageFiles) isResource(name string, named map[string]bool) bool {
	return p.isAsset(name) || resourceFormats[format(name)] || len(p.sidecars(name)) > 0 || named[p.resPath(name)]
}

// namedPaths returns the res:// paths that the package's files reference or name.
func (p *packageFiles) namedPaths() map[string]bool {
	named := map[string]bool{}
	for _, s := range p.scans {
		for _, ref := range s.refs {
			named[ref.value] = true
		}
		for _, literal := range s.literals {
			named[literal] = true
		}
	}
	return named
}

// ==== Names ===================================================================

// targetName turns a file or directory name into a lower_snake_case target name:
// `IBMPlexMono-Regular` becomes `ibm_plex_mono_regular`, `main/hud` `main_hud`.
func targetName(name string) string {
	runes := []rune(name)
	var b strings.Builder
	for i, r := range runes {
		if startsWord(runes, i) {
			b.WriteByte('_')
		}
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			b.WriteRune(unicode.ToLower(r))
		} else {
			b.WriteByte('_')
		}
	}
	parts := strings.FieldsFunc(b.String(), func(r rune) bool { return r == '_' })
	return strings.Join(parts, "_")
}

// startsWord reports whether the capital at i starts a word of a camel-case name: after a
// lowercase letter or a digit, or as the last capital of an acronym before a lowercase letter.
func startsWord(runes []rune, i int) bool {
	if i == 0 || !unicode.IsUpper(runes[i]) {
		return false
	}
	previous := runes[i-1]
	if unicode.IsLower(previous) || unicode.IsDigit(previous) {
		return true
	}
	return unicode.IsUpper(previous) && i+1 < len(runes) && unicode.IsLower(runes[i+1])
}
