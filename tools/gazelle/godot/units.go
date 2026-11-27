// Sections: Grouping, Unit names.

package godot

import (
	"path"
	"slices"
	"strings"
)

// ==== Grouping ================================================================

// A godot_resources target of the package: its files without their sidecars, and the
// entries of an existing target's srcs that name no source file of the package, such as
// labels and generated files, which it keeps. An existing target that keeps nothing is empty.
type unit struct {
	files, other []string
}

// A grouping assigns the package's resources to import units by their names.
type grouping struct {
	p       *packageFiles
	units   map[string]*unit
	claimed map[string]bool
}

// units groups the package's resources into import units by their names. An existing
// godot_resources target keeps the files its srcs list; the others form a unit per imported
// asset, named after it, with a glTF's buffers and images in the glTF's, one of the GdUnit
// suites, `suites`, and one per directory of the remaining resources, named after it. A file
// that a target of another kind lists, such as a godot_addon, belongs to no unit. It returns
// nil when an existing target's srcs are no literal list, whose files it cannot know.
func (p *packageFiles) units() map[string]*unit {
	g := &grouping{p: p, units: map[string]*unit{}, claimed: map[string]bool{}}
	if !g.claimExisting() {
		return nil
	}
	members := p.members()
	g.addGLTFs(members)
	g.addRest(members)
	return g.units
}

// claimExisting gives each existing godot_resources target the files it lists, and claims
// the files other targets list. It reports false for srcs that are no literal list.
func (g *grouping) claimExisting() bool {
	if g.p.args.File == nil {
		return true
	}
	for _, r := range g.p.args.File.Rules {
		srcs := r.AttrStrings("srcs")
		switch {
		case !isKind(g.p.args.Config, r, resourcesKind):
			g.claim(srcs...)
		case r.Attr("srcs") != nil && len(srcs) == 0:
			return false
		case r.ShouldKeep():
			g.claim(srcs...)
		default:
			g.units[r.Name()] = g.existingUnit(srcs)
		}
	}
	return true
}

func (g *grouping) claim(files ...string) {
	for _, file := range files {
		g.claimed[file] = true
	}
}

// existingUnit keeps the entries of an existing target's srcs that still name something:
// files of the package, whose sidecars follow them, labels and generated files.
func (g *grouping) existingUnit(srcs []string) *unit {
	u := &unit{}
	for _, src := range srcs {
		switch {
		case g.p.isSidecar(src):
		case g.p.has(src):
			u.files = append(u.files, src)
			g.claim(src)
		case isLabel(src) || slices.Contains(g.p.args.GenFiles, src):
			u.other = append(u.other, src)
		}
	}
	return u
}

func (g *grouping) add(name, file string) {
	u, ok := g.units[name]
	if !ok {
		u = &unit{}
		g.units[name] = u
	}
	u.files = append(u.files, file)
	g.claim(file)
}

// addGLTFs gives each glTF a unit with the buffers and images its importer reads.
func (g *grouping) addGLTFs(members []string) {
	for _, name := range members {
		if !g.claimed[name] && format(name) == ".gltf" {
			g.addGLTF(name)
		}
	}
}

func (g *grouping) addGLTF(name string) {
	unitName := g.assetName(name)
	g.add(unitName, name)
	for _, member := range g.p.scans[name].Members {
		if file, ok := g.p.fileOf(member); ok && !g.claimed[file] {
			g.add(unitName, file)
		}
	}
}

// addRest gives the suites, the directories' resources and then the assets their units, so
// that an asset's name gives way to the others.
func (g *grouping) addRest(members []string) {
	test := slices.ContainsFunc(members, g.p.isSuite)
	var assets []string
	for _, name := range members {
		switch {
		case g.claimed[name]:
		case g.p.isSuite(name):
			g.add("suites", name)
		case g.p.isAsset(name):
			assets = append(assets, name)
		default:
			g.add(g.p.directoryUnit(path.Dir(name), test), name)
		}
	}
	for _, name := range assets {
		g.add(g.assetName(name), name)
	}
}

// ==== Unit names ==============================================================

// assetName names an asset's unit after its file, with the format when another unit has
// the name.
func (g *grouping) assetName(name string) string {
	base := path.Base(name)
	unitName := targetName(strings.TrimSuffix(base, path.Ext(base)))
	if _, taken := g.units[unitName]; taken {
		unitName = targetName(base)
	}
	return unitName
}

// directoryUnit names the unit of a directory's resources: a subdirectory's after its path
// below the package, the package's own after the package, or `fixtures` in a package of
// suites, whose test takes the package's name. A project's own directory has no name of
// its own to give, since its project takes it: its unit is `resources`.
func (p *packageFiles) directoryUnit(dir string, test bool) string {
	switch {
	case dir != ".":
		return targetName(dir)
	case test:
		return "fixtures"
	case p.prefix == "":
		return "resources"
	default:
		return targetName(path.Base(p.args.Rel))
	}
}
