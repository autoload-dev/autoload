package godot

import (
	"regexp"

	"github.com/bazelbuild/bazel-gazelle/rule"
)

// keptResolveAttrs returns which of the attributes that Resolve sets an existing target
// keeps, by Gazelle's `# keep` on the attribute or on its value, with or without a reason:
// the language resolves nothing for them, and reports nothing.
func keptResolveAttrs(r *rule.Rule) map[string]bool {
	kept := map[string]bool{}
	for _, key := range []string{"deps", "runtime_deps"} {
		value := r.Attr(key)
		if value == nil {
			continue
		}
		kept[key] = rule.ShouldKeep(value)
		comments := r.AttrComments(key)
		for _, comment := range append(comments.Before, comments.Suffix...) {
			kept[key] = kept[key] || keepComment.MatchString(comment.Token)
		}
	}
	return kept
}

// Gazelle's `# keep`, alone or with a reason after `keep: `, as rule.ShouldKeep reads it.
var keepComment = regexp.MustCompile(`^#\s*keep(: .*)?\s*$`)
