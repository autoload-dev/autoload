// Sections: References, Scanning, Text resources, Other formats.

package godot

import (
	"bytes"
	"encoding/json"
	"net/url"
	"path"
	"regexp"
	"slices"
	"strings"
)

// ==== References ==============================================================

// The kind of a reference, which is also the import language of its resolve directives:
// `# gazelle:resolve godot class GdUnitTestSuite @autoload_gdunit//gdunit`.
type referenceKind int

const (
	kindRes referenceKind = iota
	kindUID
	kindClass
)

var kindNames = [...]string{kindRes: "res", kindUID: "uid", kindClass: "class"}

func (k referenceKind) String() string { return kindNames[k] }

// A reference from a file to a resource: a res:// path, a uid:// value or a global class
// name, which a target must declare as a dependency.
type reference struct {
	kind  referenceKind
	value string
}

// What a scan finds in a file: the UID and global classes it declares, a C++ source's being
// those it registers, the class or path it extends, the resources it references at load
// time, the res:// paths its other literals name, which it may load at runtime, and the
// files its importer reads.
type scanned struct {
	uid      string
	classes  []string
	extends  string
	refs     []reference
	literals []string
	members  []string
}

// resourcePath returns the res:// path a reference names: a res:// path, or a path
// relative to the directory of source, itself a res:// path. It rejects other schemes and
// paths that leave the project.
func resourcePath(value, source string) (string, bool) {
	relative, ok := strings.CutPrefix(value, "res://")
	if !ok {
		if isAbsolute(value) {
			return "", false
		}
		relative = path.Join(path.Dir(strings.TrimPrefix(source, "res://")), value)
	}
	if isAbsolute(relative) || strings.ContainsAny(relative, "\\\x00") {
		return "", false
	}
	relative = path.Clean(relative)
	if leavesProject(relative) {
		return "", false
	}
	return "res://" + relative, true
}

// isAbsolute reports whether a path has a scheme, such as user://, or a root.
func isAbsolute(value string) bool {
	return strings.Contains(value, ":") || strings.HasPrefix(value, "/")
}

func leavesProject(relative string) bool {
	return relative == "." || relative == ".." || strings.HasPrefix(relative, "../")
}

// ==== Scanning ================================================================

// The scanners of the formats whose references scan reads, by suffix.
var scanners = map[string]func(resPath string, content []byte) scanned{
	".gd":          scanScript,
	".tscn":        scanTextResource,
	".tres":        scanTextResource,
	".gdshader":    scanShader,
	".gdshaderinc": scanShader,
	".shader":      scanShader,
	".shaderinc":   scanShader,
	".gltf":        func(resPath string, content []byte) scanned { return scanned{members: gltfMembers(resPath, content)} },
	".uid":         func(_ string, content []byte) scanned { return scanned{uid: strings.TrimSpace(string(content))} },
	".import":      func(_ string, content []byte) scanned { return scanned{uid: importUID(content)} },
	".c":           scanNative,
	".cc":          scanNative,
	".cpp":         scanNative,
	".cxx":         scanNative,
	".h":           scanNative,
	".hh":          scanNative,
	".hpp":         scanNative,
}

// scannable reports whether scan reads anything in a file of the name's format.
func scannable(name string) bool {
	_, ok := scanners[format(name)]
	return ok
}

// scan reads the references of the file at the res:// path resPath, by its format. Formats
// it does not know reference nothing.
func scan(resPath string, content []byte) scanned {
	var s scanned
	if scanner, ok := scanners[format(resPath)]; ok {
		s = scanner(resPath, content)
	}
	s.refs = sortedReferences(s.refs)
	s.literals = sortedUnique(s.literals)
	return s
}

func scanNative(_ string, content []byte) scanned {
	return scanned{classes: nativeClasses(content)}
}

// addPath adds a reference to the UID or the res:// path that value names relative to
// source; an empty value names nothing.
func (s *scanned) addPath(value, source string) {
	if value == "" {
		return
	}
	if strings.HasPrefix(value, "uid://") {
		s.refs = append(s.refs, reference{kindUID, value})
		return
	}
	if resolved, ok := resourcePath(value, source); ok {
		s.refs = append(s.refs, reference{kindRes, resolved})
	}
}

func sortedReferences(refs []reference) []reference {
	slices.SortFunc(refs, func(a, b reference) int {
		if a.kind != b.kind {
			return int(a.kind) - int(b.kind)
		}
		return strings.Compare(a.value, b.value)
	})
	return slices.Compact(refs)
}

func sortedUnique(values []string) []string {
	slices.Sort(values)
	return slices.Compact(values)
}

// ==== Text resources ==========================================================

// A section header of a text scene or resource, such as `[ext_resource path="…" id="1"]`,
// and its attributes.
var (
	headerPattern    = regexp.MustCompile(`^\[(\w+)((?:\s+\w+=(?:"(?:[^"\\]|\\.)*"|[^\s\]]+))*)\s*\]$`)
	attributePattern = regexp.MustCompile(`(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)`)
	literalPattern   = regexp.MustCompile(`"(res://[^"\\]+)"`)
)

// scanTextResource reads a .tscn or .tres file: the UID of its header, the paths and UIDs
// of its external resources and the res:// paths its property values name.
func scanTextResource(resPath string, content []byte) scanned {
	var s scanned
	for _, line := range strings.Split(string(content), "\n") {
		section, attributes, ok := sectionHeader(line)
		switch {
		case !ok:
			s.literals = append(s.literals, literalPaths(line, resPath)...)
		case section == "gd_scene" || section == "gd_resource":
			s.uid = attributes["uid"]
		case section == "ext_resource":
			s.addPath(attributes["uid"], resPath)
			s.addPath(attributes["path"], resPath)
		}
	}
	return s
}

// sectionHeader parses a line that is a section header into its name and attributes.
func sectionHeader(line string) (string, map[string]string, bool) {
	match := headerPattern.FindStringSubmatch(strings.TrimSpace(line))
	if match == nil {
		return "", nil, false
	}
	attributes := map[string]string{}
	for _, attribute := range attributePattern.FindAllStringSubmatch(match[2], -1) {
		attributes[attribute[1]] = strings.Trim(attribute[2], `"`)
	}
	return match[1], attributes, true
}

// literalPaths returns the res:// paths of a line's string literals.
func literalPaths(line, resPath string) []string {
	var paths []string
	for _, literal := range literalPattern.FindAllStringSubmatch(line, -1) {
		if resolved, ok := resourcePath(literal[1], resPath); ok {
			paths = append(paths, resolved)
		}
	}
	return paths
}

// ==== Other formats ===========================================================

var includePattern = regexp.MustCompile(`(?m)^\s*#include\s+"([^"]+)"`)

// scanShader reads the paths of a shader's #include directives.
func scanShader(resPath string, content []byte) scanned {
	var s scanned
	for _, match := range includePattern.FindAllSubmatch(content, -1) {
		s.addPath(string(match[1]), resPath)
	}
	return s
}

var importUIDPattern = regexp.MustCompile(`(?m)^uid="(uid://[^"]+)"`)

// importUID returns the UID of an imported file from its .import sidecar.
func importUID(content []byte) string {
	if match := importUIDPattern.FindSubmatch(content); match != nil {
		return string(match[1])
	}
	return ""
}

// gltfMembers returns the files a glTF's importer reads: its external buffers and images,
// as res:// paths. Embedded data URIs read nothing.
func gltfMembers(resPath string, content []byte) []string {
	var gltf struct {
		Buffers, Images []struct{ URI string }
	}
	if json.NewDecoder(bytes.NewReader(content)).Decode(&gltf) != nil {
		return nil
	}
	var members []string
	for _, entry := range append(gltf.Buffers, gltf.Images...) {
		if entry.URI == "" || strings.HasPrefix(entry.URI, "data:") {
			continue
		}
		uri, err := url.PathUnescape(entry.URI)
		if err != nil {
			continue
		}
		if resolved, ok := resourcePath(uri, resPath); ok {
			members = append(members, resolved)
		}
	}
	return sortedUnique(members)
}

// How an extension registers a class with Godot's ClassDB: godot-cpp's and a module's
// register_class templates and the engine's GDREGISTER macros.
var registrationPattern = regexp.MustCompile(
	`register_(?:abstract_|internal_|runtime_|virtual_)?class<\s*(\w+)\s*>|GDREGISTER_(?:ABSTRACT_|INTERNAL_|RUNTIME_|VIRTUAL_)?CLASS\(\s*(\w+)\s*\)`,
)

// nativeClasses returns the classes a C++ source of an extension registers.
func nativeClasses(content []byte) []string {
	var classes []string
	for _, match := range registrationPattern.FindAllSubmatch(content, -1) {
		classes = append(classes, string(match[1])+string(match[2]))
	}
	return sortedUnique(classes)
}
