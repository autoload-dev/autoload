// Package lint is a Gazelle language that declares, in each package, a filegroup per kind of
// source the lint check reads: Markdown and GDScript, which have no targets of their own, and
// Python, Starlark and C++, whose files the convention rules that judge each file on its own
// read (tools/conventions/files.py). Each
// filegroup lists the package's files of its kind, those of its subdirectories that are no
// packages included, and carries the kind as its tag, by which the lint check's aspects find
// it (tools/lint/check.bzl). Only files that Git lists, tracked or untracked and not ignored,
// are declared; Gazelle walks every file on disk.
//
// Sections: Kinds, Language.
package lint

import (
	"flag"
	"os/exec"
	"path"
	"slices"
	"sort"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/bazel-gazelle/label"
	"github.com/bazelbuild/bazel-gazelle/language"
	"github.com/bazelbuild/bazel-gazelle/rule"
)

// ==== Kinds ===================================================================

// A kind of source: the filegroup's name and tag, the suffixes of its files and the names of
// those it holds whatever their suffix.
type kind struct {
	name, tag string
	suffixes  []string
	names     []string
}

var kinds = []kind{
	{name: "cc_files", tag: "cc", suffixes: []string{".cc", ".cpp", ".h"}},
	{name: "gdscript_files", tag: "gdscript", suffixes: []string{".gd"}},
	{name: "markdown_files", tag: "markdown", suffixes: []string{".md"}},
	// rules_lint's Python linters visit filegroups tagged `python` of their own accord.
	{name: "python_files", tag: "python_files", suffixes: []string{".py"}},
	{
		name:     "starlark_files",
		tag:      "starlark",
		suffixes: []string{".bzl", "MODULE.bazel"},
		names:    []string{"BUILD", "BUILD.bazel"},
	},
}

// holds reports whether a file, by its path, is of the kind.
func (k kind) holds(name string) bool {
	base := path.Base(name)
	return slices.Contains(k.names, base) || slices.ContainsFunc(k.suffixes, func(suffix string) bool {
		return strings.HasSuffix(base, suffix)
	})
}

// filegroup declares the files of a kind.
func (k kind) filegroup(files []string) *rule.Rule {
	r := rule.NewRule("filegroup", k.name)
	r.SetAttr("srcs", files)
	r.SetAttr("tags", []string{k.tag})
	// Only the lint check reads them, as top-level targets: they may hold files of a test
	// scope (RG012), and they are no API of a package that is public by default.
	r.SetAttr("testonly", true)
	r.SetAttr("visibility", []string{"//visibility:private"})
	return r
}

// listed returns the files Git lists below root, relative to it, or nil outside a checkout.
func listed(root string) map[string]bool {
	out, err := exec.Command(
		"git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard",
	).Output()
	if err != nil {
		return nil
	}
	files := map[string]bool{}
	for _, name := range strings.Split(string(out), "\x00") {
		if name != "" {
			files[name] = true
		}
	}
	return files
}

// ==== Language ================================================================

type lintLang struct {
	language.BaseLang
	// The files Git lists in the repository, by path relative to its root; nil keeps all.
	listed map[string]bool
	// The files of each directory that is no package, with those of its subdirectories that
	// are none, relative to it; its package's filegroups list them.
	pending map[string][]string
}

// NewLanguage is the entry point gazelle_binary calls.
func NewLanguage() language.Language {
	return &lintLang{pending: map[string][]string{}}
}

func (*lintLang) Name() string { return "lint" }

func (l *lintLang) CheckFlags(_ *flag.FlagSet, c *config.Config) error {
	l.listed = listed(c.RepoRoot)
	return nil
}

func (*lintLang) Kinds() map[string]rule.KindInfo {
	return map[string]rule.KindInfo{
		"filegroup": {
			NonEmptyAttrs:  map[string]bool{"srcs": true},
			MergeableAttrs: map[string]bool{
				"srcs":       true,
				"tags":       true,
				"testonly":   true,
				"visibility": true,
			},
		},
	}
}

// Loads names no file: filegroup is native.
func (*lintLang) Loads() []rule.LoadInfo { return nil }

func (*lintLang) Fix(*config.Config, *rule.File) {}

// files returns the directory's files that Git lists, with those of its subdirectories that
// are no packages, relative to the directory. Gazelle visits subdirectories first.
func (l *lintLang) files(args language.GenerateArgs) []string {
	var files []string
	for _, name := range args.RegularFiles {
		if l.listed == nil || l.listed[path.Join(args.Rel, name)] {
			files = append(files, name)
		}
	}
	for _, sub := range args.Subdirs {
		for _, name := range l.pending[path.Join(args.Rel, sub)] {
			files = append(files, path.Join(sub, name))
		}
	}
	sort.Strings(files)
	return files
}

func (l *lintLang) GenerateRules(args language.GenerateArgs) language.GenerateResult {
	files := l.files(args)
	if args.File == nil {
		// No package: the nearest package above declares the directory's files.
		l.pending[args.Rel] = files
		return language.GenerateResult{}
	}
	var result language.GenerateResult
	for _, k := range kinds {
		var matching []string
		for _, name := range files {
			if k.holds(name) {
				matching = append(matching, name)
			}
		}
		if len(matching) == 0 {
			// Gazelle removes the filegroup of a kind the package no longer holds.
			result.Empty = append(result.Empty, rule.NewRule("filegroup", k.name))
			continue
		}
		result.Gen = append(result.Gen, k.filegroup(matching))
		result.Imports = append(result.Imports, nil)
	}
	return result
}

// Embeds and Resolve leave the filegroups as generated: they depend on nothing.
func (*lintLang) Embeds(*rule.Rule, label.Label) []label.Label { return nil }
