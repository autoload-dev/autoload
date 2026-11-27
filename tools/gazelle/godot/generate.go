// Sections: Generation, Targets.

package godot

import (
	"log"
	"maps"
	"path"
	"slices"

	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// ==== Generation ==============================================================

// What Resolve receives for a godot_resources target: the references of its files, and the
// res:// paths their other literals name.
type unitImports struct {
	refs     []reference
	literals []string
}

// generates reports whether the language declares anything in the directory.
func (gc *godotConfig) generates() bool {
	return gc.enabled && gc.project != nil && !gc.ignored
}

func (l *godotLang) GenerateRules(args language.GenerateArgs) language.GenerateResult {
	gc := getConfig(args.Config)
	if !gc.generates() {
		return language.GenerateResult{}
	}
	files := l.directoryFiles(args)
	if !gc.isPackage(args) {
		// The nearest package above declares the directory's files.
		l.pending[args.Rel] = files
		return language.GenerateResult{}
	}
	p := l.newPackageFiles(args, gc.project, files)
	var result language.GenerateResult
	if p.prefix == "" {
		add(&result, p.projectRule(), nil)
	}
	units := p.units()
	if units == nil {
		log.Printf("%s: a godot_resources target's srcs are no list of files; leaving the package's resources as they are", args.Rel)
		return result
	}
	if suites := p.addResources(&result, units); gc.tests && p.needsTest(suites) {
		add(&result, p.testRule(suites), nil)
	}
	return result
}

// isPackage reports whether a directory is a package: one with a BUILD file, or a project's.
func (gc *godotConfig) isPackage(args language.GenerateArgs) bool {
	return args.File != nil || gc.project.rel == args.Rel
}

func add(result *language.GenerateResult, r *rule.Rule, imports interface{}) {
	result.Gen = append(result.Gen, r)
	result.Imports = append(result.Imports, imports)
}

// addResources declares the units in the order of their names, an empty one as empty, and
// returns the labels of those that hold suites.
func (p *packageFiles) addResources(result *language.GenerateResult, units map[string]*unit) []string {
	var suites []string
	for _, name := range slices.Sorted(maps.Keys(units)) {
		u := units[name]
		if len(u.files) == 0 && len(u.other) == 0 {
			result.Empty = append(result.Empty, rule.NewRule(resourcesKind, name))
			continue
		}
		r, imports := p.resourcesRule(name, u)
		add(result, r, imports)
		if slices.ContainsFunc(u.files, p.isSuite) {
			suites = append(suites, ":"+name)
		}
	}
	return suites
}

// ==== Targets =================================================================

func (p *packageFiles) projectRule() *rule.Rule {
	r := rule.NewRule(projectKind, p.project.label.Name)
	r.SetAttr("project_file", projectFile)
	if p.args.File == nil {
		// A new package's packages below name the project.
		r.SetAttr("visibility", []string{"//" + p.args.Rel + ":__subpackages__"})
	}
	return r
}

// resourcesRule declares a unit and gathers the references of its files.
func (p *packageFiles) resourcesRule(name string, u *unit) (*rule.Rule, unitImports) {
	srcs := slices.Clone(u.other)
	var imports unitImports
	for _, file := range u.files {
		srcs = append(srcs, file)
		srcs = append(srcs, p.sidecars(file)...)
		imports.refs = append(imports.refs, p.scans[file].Refs...)
		imports.literals = append(imports.literals, p.scans[file].Runtime...)
	}
	slices.Sort(srcs)
	imports.refs = sortedReferences(imports.refs)
	imports.literals = sortedUnique(imports.literals)
	r := rule.NewRule(resourcesKind, name)
	r.SetAttr("srcs", slices.Compact(srcs))
	if p.prefix != "" {
		r.SetAttr("prefix", p.prefix)
	}
	return r, imports
}

func (p *packageFiles) testRule(suites []string) *rule.Rule {
	r := rule.NewRule(gdunitTestKind, p.testName())
	r.SetAttr("project", p.project.label.Rel("", p.args.Rel).String())
	r.SetAttr("suites", suites)
	return r
}

// testName names the package's GdUnit test after the package, or `tests` in the project's own
// package, whose project takes its name.
func (p *packageFiles) testName() string {
	if p.prefix == "" {
		return "tests"
	}
	return targetName(path.Base(p.args.Rel))
}

// needsTest reports whether the package's suites need a generated test: there are some, and
// no test of a person's runs a part of them.
func (p *packageFiles) needsTest(suites []string) bool {
	return len(suites) > 0 && !p.testedByHand(suites)
}

// testedByHand reports whether a gdunit_test of the package already runs some of its suites
// but not all of them, as a person chose.
func (p *packageFiles) testedByHand(suites []string) bool {
	if p.args.File == nil {
		return false
	}
	for _, r := range p.args.File.Rules {
		if isKind(p.args.Config, r, gdunitTestKind) && runsSomeOf(r, suites) {
			return true
		}
	}
	return false
}

func runsSomeOf(test *rule.Rule, suites []string) bool {
	runs := test.AttrStrings("suites")
	slices.Sort(runs)
	return !slices.Equal(runs, suites) && slices.ContainsFunc(runs, func(s string) bool { return slices.Contains(suites, s) })
}
