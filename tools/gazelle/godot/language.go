// Package godot is a Gazelle language that declares the Godot projects, resources and GdUnit
// tests of rules_godot: a godot_project beside each project.godot, a godot_resources target
// per import unit of each Bazel package inside a project, with the dependencies its files
// reference, and a gdunit_test for each package that holds GdUnit suites. The design, the
// attributes it owns and its directives are in docs/internal/gazelle.md.
//
// Sections: Language, Configuration.
package godot

import (
	"flag"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/label"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// ==== Language ================================================================

const languageName = "godot"

// The kinds this language generates, and those whose targets it only indexes: add-ons and
// extensions, which scripts reach by their resource paths.
const (
	projectKind       = "godot_project"
	resourcesKind     = "godot_resources"
	gdunitTestKind    = "gdunit_test"
	addonKind         = "godot_addon"
	extensionKind     = "godot_extension"
	ccExtensionKind   = "godot_cc_extension"
	rulesGodotModule  = "autoload_rules_godot"
	gdunitModule      = "autoload_gdunit"
	projectFile       = "project.godot"
	gdignoreFile      = ".gdignore"
	suiteBaseClass    = "GdUnitTestSuite"
	extensionDirective = "godot_extension"
	testDirective      = "godot_gdunit_test"
)

type godotLang struct {
	language.BaseLang
	// The files of each directory that is no Bazel package, with those of its
	// subdirectories that are none either, relative to it; the nearest package above lists
	// them. Gazelle generates subdirectories first.
	pending map[string][]string
	language.BaseLifecycleManager
	// What the scanner found in each file, by its absolute path, and the scanner process.
	scans   map[string]scanned
	scanner *scanner
}

// NewLanguage is the entry point gazelle_binary calls.
func NewLanguage() language.Language {
	return &godotLang{pending: map[string][]string{}, scans: map[string]scanned{}}
}

func (*godotLang) Name() string { return languageName }

func (*godotLang) Kinds() map[string]rule.KindInfo {
	return map[string]rule.KindInfo{
		// A target a person renamed still matches by what it declares.
		projectKind: {
			MatchAttrs:     []string{"project_file"},
			NonEmptyAttrs:  map[string]bool{"project_file": true},
			MergeableAttrs: map[string]bool{"project_file": true},
		},
		resourcesKind: {
			NonEmptyAttrs: map[string]bool{"srcs": true},
			MergeableAttrs: map[string]bool{
				"prefix":       true,
				"srcs":         true,
				"strip_prefix": true,
			},
			ResolveAttrs: map[string]bool{"deps": true, "runtime_deps": true},
		},
		gdunitTestKind: {
			MatchAttrs:     []string{"suites"},
			NonEmptyAttrs:  map[string]bool{"suites": true},
			MergeableAttrs: map[string]bool{"project": true, "suites": true},
		},
		addonKind:       {},
		extensionKind:   {},
		ccExtensionKind: {},
	}
}

func (l *godotLang) Loads() []rule.LoadInfo {
	return l.ApparentLoads(func(string) string { return "" })
}

// ApparentLoads names the rules' files by the repositories under which the module that
// runs Gazelle sees autoload_rules_godot and autoload_gdunit.
func (*godotLang) ApparentLoads(moduleToApparentName func(string) string) []rule.LoadInfo {
	repository := func(module string) string {
		if name := moduleToApparentName(module); name != "" {
			return name
		}
		return module
	}
	return []rule.LoadInfo{
		{
			Name:    "@" + repository(rulesGodotModule) + "//godot:defs.bzl",
			Symbols: []string{projectKind, resourcesKind},
		},
		{
			Name:    "@" + repository(gdunitModule) + "//gdunit:defs.bzl",
			Symbols: []string{gdunitTestKind},
		},
	}
}

func (*godotLang) Fix(*config.Config, *rule.File) {}

func (*godotLang) Embeds(*rule.Rule, label.Label) []label.Label { return nil }

// ==== Configuration ===========================================================

// A Godot project: the directory of its project.godot, relative to the repository's root,
// and its godot_project target.
type project struct {
	rel   string
	label label.Label
}

// The configuration of a directory.
type godotConfig struct {
	// Whether the language generates in the directory: `# gazelle:godot_extension
	// enabled|disabled`.
	enabled bool
	// Whether the language declares GdUnit tests: `# gazelle:godot_gdunit_test
	// enabled|disabled`.
	tests bool
	// The project the directory belongs to, nil outside every project.
	project *project
	// Whether Godot skips the directory: it or a directory above holds a .gdignore, or its
	// name begins with a dot.
	ignored bool
}

func getConfig(c *config.Config) *godotConfig {
	if gc, ok := c.Exts[languageName].(*godotConfig); ok {
		return gc
	}
	return &godotConfig{enabled: true, tests: true}
}

func (*godotLang) RegisterFlags(*flag.FlagSet, string, *config.Config) {}

func (*godotLang) CheckFlags(*flag.FlagSet, *config.Config) error { return nil }

func (*godotLang) KnownDirectives() []string {
	return []string{extensionDirective, testDirective}
}

func (*godotLang) Configure(c *config.Config, rel string, f *rule.File) {
	gc := *getConfig(c)
	if f != nil {
		gc.applyDirectives(f.Directives)
	}
	dir := filepath.Join(c.RepoRoot, filepath.FromSlash(rel))
	switch {
	case exists(filepath.Join(dir, projectFile)):
		// Godot scans a project's root whatever it holds.
		gc.project = &project{rel: rel, label: label.New("", rel, projectName(c, rel, f))}
		gc.ignored = false
	case exists(filepath.Join(dir, gdignoreFile)) || isHidden(rel):
		gc.ignored = true
	}
	c.Exts[languageName] = &gc
}

func (gc *godotConfig) applyDirectives(directives []rule.Directive) {
	for _, d := range directives {
		switch d.Key {
		case extensionDirective:
			gc.enabled = d.Value != "disabled"
		case testDirective:
			gc.tests = d.Value != "disabled"
		}
	}
}

// isHidden reports whether a directory's name begins with a dot, which hides it from Godot.
func isHidden(rel string) bool {
	return rel != "" && strings.HasPrefix(path.Base(rel), ".")
}

// projectName returns the name of the project's godot_project: the existing one's, else the
// directory's name.
func projectName(c *config.Config, rel string, f *rule.File) string {
	if f != nil {
		for _, r := range f.Rules {
			if isKind(c, r, projectKind) && r.AttrString("project_file") == projectFile {
				return r.Name()
			}
		}
	}
	if rel == "" {
		return "project"
	}
	return targetName(path.Base(rel))
}

// isKind reports whether a rule is of the kind, or of the kind a map_kind directive maps it to.
func isKind(c *config.Config, r *rule.Rule, kind string) bool {
	if r.Kind() == kind {
		return true
	}
	mapped, ok := c.KindMap[kind]
	return ok && r.Kind() == mapped.KindName
}

func exists(name string) bool {
	_, err := os.Stat(name)
	return err == nil
}
