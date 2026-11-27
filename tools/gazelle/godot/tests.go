package godot

import (
	"path"
	"slices"

	"github.com/bazelbuild/bazel-gazelle/label"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// testRule declares the GdUnit test of the package's suites.
func (p *packageFiles) testRule(name string, suites []string) *rule.Rule {
	r := rule.NewRule(gdunitTestKind, name)
	r.SetAttr("project", p.project.label.Rel("", p.args.Rel).String())
	r.SetAttr("suites", suites)
	return r
}

// defaultTestName names the package's GdUnit test after the package, or `tests` in the
// project's own package, whose project takes its name.
func (p *packageFiles) defaultTestName() string {
	if p.prefix == "" {
		return "tests"
	}
	return targetName(path.Base(p.args.Rel))
}

// testName names the test of the package's suites: the existing test that runs them all,
// else the default name. A package without suites, or whose suites a person's test runs in
// part, gets none.
func (p *packageFiles) testName(suites []string) (string, bool) {
	if len(suites) == 0 {
		return "", false
	}
	for _, r := range p.existingTests() {
		runs := p.labels(r.AttrStrings("suites"))
		if slices.Equal(runs, p.labels(suites)) {
			return r.Name(), true
		}
		if slices.ContainsFunc(runs, func(l string) bool { return slices.Contains(p.labels(suites), l) }) {
			return "", false
		}
	}
	return p.defaultTestName(), true
}

func (p *packageFiles) existingTests() []*rule.Rule {
	if p.args.File == nil {
		return nil
	}
	return slices.DeleteFunc(slices.Clone(p.args.File.Rules), func(r *rule.Rule) bool {
		return !isKind(p.args.Config, r, gdunitTestKind)
	})
}

// labels returns labels in one spelling, absolute and sorted, so that `suites`, `:suites`
// and `//pkg:suites` compare equal.
func (p *packageFiles) labels(values []string) []string {
	var spelled []string
	for _, l := range p.absolute(values) {
		spelled = append(spelled, l.String())
	}
	return sortedUnique(spelled)
}

// absolute returns the labels among values, absolute in the package's repository.
func (p *packageFiles) absolute(values []string) []label.Label {
	var labels []label.Label
	for _, value := range values {
		if l, err := label.Parse(value); err == nil {
			labels = append(labels, l.Abs(p.args.Config.RepoName, p.args.Rel))
		}
	}
	return labels
}
