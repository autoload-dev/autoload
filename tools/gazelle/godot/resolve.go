// Sections: Index, Resolution.

package godot

import (
	"log"
	"maps"
	"path"
	"slices"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/label"
	"github.com/bazelbuild/bazel-gazelle/pathtools"
	"github.com/bazelbuild/bazel-gazelle/repo"
	"github.com/bazelbuild/bazel-gazelle/resolve"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// ==== Index ===================================================================

// The index holds what targets provide: the res:// paths of their files, the UIDs those
// declare and the global classes their scripts declare. A res:// path and a class name hold
// within one project, so a target inside a project provides them as `<value>@<project
// directory>`, one outside every project, such as an add-on's, provides them plain. UIDs are
// unique across projects.
func qualified(value string, p *project) string {
	if p == nil {
		return value
	}
	return value + "@" + p.rel
}

func importSpec(value string) resolve.ImportSpec {
	return resolve.ImportSpec{Lang: languageName, Imp: value}
}

// An importer gathers what one target provides.
type importer struct {
	lang    *godotLang
	c       *config.Config
	project *project
	pkg     string
	specs   []resolve.ImportSpec
}

// add records a value the target provides; one that holds within a project is qualified.
func (im *importer) add(value string, inProject bool) {
	if inProject {
		value = qualified(value, im.project)
	}
	im.specs = append(im.specs, importSpec(value))
}

// Imports indexes godot_resources targets by their files, add-ons and extensions by the
// resource paths Godot loads them from, an add-on's directory, as `res://<directory>/` (by
// default `addons/<name>`), and an extension's .gdextension file, and extensions by the
// classes their C++ sources in the package register.
func (l *godotLang) Imports(c *config.Config, r *rule.Rule, f *rule.File) []resolve.ImportSpec {
	im := &importer{lang: l, c: c, project: getConfig(c).project, pkg: f.Pkg}
	switch {
	case isKind(c, r, resourcesKind):
		im.resources(r)
	case isKind(c, r, addonKind):
		im.addon(r)
	case isKind(c, r, extensionKind), isKind(c, r, ccExtensionKind):
		im.extension(r)
	}
	return im.specs
}

func (im *importer) resources(r *rule.Rule) {
	prefix, strip := r.AttrString("prefix"), r.AttrString("strip_prefix")
	srcs := sourceFiles(r)
	resPaths := make([]string, len(srcs))
	for i, src := range srcs {
		resPaths[i] = "res://" + path.Join(prefix, pathtools.TrimPrefix(src, strip))
	}
	for i, s := range im.scan(srcs, resPaths) {
		im.resourceFile(srcs[i], resPaths[i], s)
	}
}

// scan returns what the scanner finds in files of the target's package.
func (im *importer) scan(srcs, resPaths []string) []scanned {
	rels := make([]string, len(srcs))
	for i, src := range srcs {
		rels[i] = path.Join(im.pkg, src)
	}
	return im.lang.scanFiles(im.c, rels, resPaths)
}

// resourceFile records what a file of a godot_resources target provides: the UID it or its
// sidecar declares, and a file's res:// path and global classes.
func (im *importer) resourceFile(src, resPath string, s scanned) {
	for _, uid := range s.UIDs {
		im.add(uid, false)
	}
	if sidecarSource(src) != "" {
		return
	}
	im.add(resPath, true)
	for _, class := range s.Classes {
		im.add(class, true)
	}
}

func (im *importer) addon(r *rule.Rule) {
	directory := r.AttrString("directory")
	if directory == "" {
		directory = "addons/" + r.Name()
	}
	im.add("res://"+strings.Trim(directory, "/")+"/", true)
}

func (im *importer) extension(r *rule.Rule) {
	if resourcePath := r.AttrString("resource_path"); resourcePath != "" {
		im.add("res://"+resourcePath, true)
	}
	srcs := sourceFiles(r)
	resPaths := make([]string, len(srcs))
	for i, src := range srcs {
		resPaths[i] = "res://" + src
	}
	for _, s := range im.scan(srcs, resPaths) {
		for _, class := range s.Classes {
			im.add(class, true)
		}
	}
}

// sourceFiles returns the entries of a target's srcs that name files of its package.
func sourceFiles(r *rule.Rule) []string {
	return slices.DeleteFunc(r.AttrStrings("srcs"), isLabel)
}

func isLabel(src string) bool {
	return strings.HasPrefix(src, ":") || strings.HasPrefix(src, "@") || strings.Contains(src, "//")
}

// ==== Resolution ==============================================================

// A resolver finds the targets that provide the references of one target.
type resolver struct {
	c       *config.Config
	ix      *resolve.RuleIndex
	project *project
	from    label.Label
}

// Resolve sets a godot_resources target's deps to the targets that provide what its files
// reference at load time, and its runtime_deps to those that provide the other res:// paths
// their literals name, which a script may load at runtime.
//
// Gazelle's resolve.Resolver interface defines the parameters.
// @codescene(disable:"Excess Number of Function Arguments")
func (l *godotLang) Resolve(c *config.Config, ix *resolve.RuleIndex, _ *repo.RemoteCache, r *rule.Rule, imports interface{}, from label.Label) {
	ui, ok := imports.(unitImports)
	if !ok {
		return
	}
	rv := resolver{c: c, ix: ix, project: getConfig(c).project, from: from}
	deps := rv.all(ui.refs, nil)
	runtime := make([]reference, 0, len(ui.literals))
	for _, literal := range ui.literals {
		runtime = append(runtime, reference{Kind: kindRes, Value: literal})
	}
	setLabels(r, "deps", deps)
	setLabels(r, "runtime_deps", rv.all(runtime, deps))
}

// all returns the labels, relative to the target, of the targets that provide the
// references, leaving out those in skip.
func (rv resolver) all(refs []reference, skip map[string]bool) map[string]bool {
	found := map[string]bool{}
	for _, ref := range refs {
		if dep, ok := rv.lookup(ref); ok {
			if rel := dep.Rel(rv.from.Repo, rv.from.Pkg).String(); !skip[rel] {
				found[rel] = true
			}
		}
	}
	return found
}

func setLabels(r *rule.Rule, key string, labels map[string]bool) {
	if len(labels) == 0 {
		r.DelAttr(key)
		return
	}
	r.SetAttr(key, slices.Sorted(maps.Keys(labels)))
}

// lookup finds the target that provides a reference: the one a resolve directive names, else
// the one the index holds, in the referencing project before outside every project. A
// res:// path is also provided by the add-on whose directory holds it. A reference no target
// provides, such as one to a built-in class, resolves to nothing; one to the referencing
// target itself too.
func (rv resolver) lookup(ref reference) (label.Label, bool) {
	if dep, ok := rv.override(ref); ok {
		return dep, dep != label.NoLabel && !dep.Equal(rv.from)
	}
	for _, value := range candidates(ref) {
		for _, key := range []string{qualified(value, rv.project), value} {
			if results := rv.ix.FindRulesByImportWithConfig(rv.c, importSpec(key), languageName); len(results) > 0 {
				return rv.choose(ref, results)
			}
		}
	}
	return label.NoLabel, false
}

// override returns the target a resolve directive names for the reference: one for its
// kind, such as `class`, or one for the language.
func (rv resolver) override(ref reference) (label.Label, bool) {
	for _, lang := range []string{string(ref.Kind), languageName} {
		if dep, ok := resolve.FindRuleWithOverride(rv.c, importSpec(ref.Value), lang); ok {
			return dep, true
		}
	}
	return label.NoLabel, false
}

// choose picks the target among those the index holds for a reference: none when the
// referencing target is among them, which another target may share a file with, and none,
// with a message, when several provide it.
func (rv resolver) choose(ref reference, results []resolve.FindResult) (label.Label, bool) {
	if slices.ContainsFunc(results, func(r resolve.FindResult) bool { return r.IsSelfImport(rv.from) }) {
		return label.NoLabel, false
	}
	if len(results) > 1 {
		log.Printf("%s: %s %s is provided by several targets, %s and %s; add a resolve directive", rv.from, ref.Kind, ref.Value, results[0].Label, results[1].Label)
		return label.NoLabel, false
	}
	return results[0].Label, true
}

// candidates returns the index keys that may provide a reference, the most specific first: a
// res:// path itself, then each directory above it.
func candidates(ref reference) []string {
	values := []string{ref.Value}
	if ref.Kind != kindRes {
		return values
	}
	for dir := path.Dir(strings.TrimPrefix(ref.Value, "res://")); dir != "."; dir = path.Dir(dir) {
		values = append(values, "res://"+dir+"/")
	}
	return values
}
