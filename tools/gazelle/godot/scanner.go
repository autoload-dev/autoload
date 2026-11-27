// Sections: Scans, Scanner process.

package godot

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"

	"github.com/bazelbuild/bazel-gazelle/config"
	"github.com/bazelbuild/rules_go/go/runfiles"
)

// ==== Scans ===================================================================

// The kind of a reference, which is also the import language of its resolve directives:
// `# gazelle:resolve godot class GdUnitTestSuite @autoload_gdunit//gdunit`.
type referenceKind string

const (
	kindRes   referenceKind = "res"
	kindUID   referenceKind = "uid"
	kindClass referenceKind = "class"
)

// A reference from a file to a resource: a res:// path, a uid:// value or a global class
// name, which a target must declare as a dependency.
type reference struct {
	Kind  referenceKind `json:"kind"`
	Value string        `json:"value"`
}

// What the scanner finds in a file (scanner.py): the UIDs it authors, the global classes it
// declares, or a C++ source registers, the class it extends by name, the references it makes
// at load time, the res:// paths it reads at runtime and the files its importer reads.
type scanned struct {
	UIDs    []string    `json:"uids"`
	Classes []string    `json:"classes"`
	Extends string      `json:"extends"`
	Refs    []reference `json:"refs"`
	Runtime []string    `json:"runtime"`
	Members []string    `json:"members"`
}

// A file to scan: its path on disk and its res:// path.
type scanFile struct {
	File string `json:"file"`
	Path string `json:"path"`
}

// scanFiles returns what the scanner finds in files of the repository, given by their paths
// relative to its root and their res:// paths; it scans each file once per run.
func (l *godotLang) scanFiles(c *config.Config, rels, resPaths []string) []scanned {
	var missing []scanFile
	keys := make([]string, len(rels))
	for i, rel := range rels {
		keys[i] = filepath.Join(c.RepoRoot, filepath.FromSlash(rel))
		if _, ok := l.scans[keys[i]]; !ok {
			missing = append(missing, scanFile{File: keys[i], Path: resPaths[i]})
		}
	}
	if len(missing) > 0 {
		for i, s := range l.process().scan(missing) {
			l.scans[missing[i].File] = s
		}
	}
	results := make([]scanned, len(keys))
	for i, key := range keys {
		results[i] = l.scans[key]
	}
	return results
}

func sortedReferences(refs []reference) []reference {
	slices.SortFunc(refs, func(a, b reference) int {
		if a.Kind != b.Kind {
			return strings.Compare(string(a.Kind), string(b.Kind))
		}
		return strings.Compare(a.Value, b.Value)
	})
	return slices.Compact(refs)
}

func sortedUnique(values []string) []string {
	slices.Sort(values)
	return slices.Compact(values)
}

// ==== Scanner process =========================================================

// The scanner's path in the runfiles, which the BUILD file sets, and the variable that
// names another scanner program instead.
var scannerRlocation string

const scannerVariable = "GAZELLE_GODOT_SCANNER"

// A scanner process: the language starts one per run when it first scans and stops it once
// Gazelle resolved the dependencies. It answers each request line with one line.
type scanner struct {
	cmd      *exec.Cmd
	requests io.WriteCloser
	encoder  *json.Encoder
	answers  *json.Decoder
}

// process returns the run's scanner process, which it starts on first use.
func (l *godotLang) process() *scanner {
	if l.scanner == nil {
		l.scanner = startScanner(context.Background())
	}
	return l.scanner
}

// startScanner starts the scanner program with the runfiles of this binary, or the one that
// GAZELLE_GODOT_SCANNER names. Gazelle cannot generate without it, so a failure ends the run.
func startScanner(ctx context.Context) *scanner {
	program, env := os.Getenv(scannerVariable), []string(nil)
	if program == "" {
		files, err := runfiles.New()
		if err != nil {
			log.Fatalf("godot: cannot find the runfiles of the scanner: %v", err)
		}
		if program, err = files.Rlocation(scannerRlocation); err != nil {
			log.Fatalf("godot: cannot find the scanner %s: %v", scannerRlocation, err)
		}
		env = files.Env()
	}
	cmd := exec.CommandContext(ctx, program)
	cmd.Env = append(os.Environ(), env...)
	cmd.Stderr = os.Stderr
	requests, err := cmd.StdinPipe()
	if err != nil {
		log.Fatalf("godot: cannot write to the scanner: %v", err)
	}
	answers, err := cmd.StdoutPipe()
	if err != nil {
		log.Fatalf("godot: cannot read from the scanner: %v", err)
	}
	if err := cmd.Start(); err != nil {
		log.Fatalf("godot: cannot start the scanner %s: %v", program, err)
	}
	return &scanner{
		cmd:      cmd,
		requests: requests,
		encoder:  json.NewEncoder(requests),
		answers:  json.NewDecoder(bufio.NewReader(answers)),
	}
}

// scan sends one request and reads its answer.
func (s *scanner) scan(files []scanFile) []scanned {
	if err := s.encoder.Encode(map[string][]scanFile{"files": files}); err != nil {
		log.Fatalf("godot: cannot send files to the scanner: %v", err)
	}
	var answer struct {
		Files []scanned `json:"files"`
	}
	if err := s.answers.Decode(&answer); err != nil || len(answer.Files) != len(files) {
		log.Fatalf("godot: the scanner gave no answer for %d files: %v", len(files), err)
	}
	return answer.Files
}

// stop ends the scanner's input and waits for it to exit.
func (s *scanner) stop() {
	s.requests.Close()
	if err := s.cmd.Wait(); err != nil {
		log.Printf("godot: the scanner failed: %v", err)
	}
}

// AfterResolvingDeps stops the scanner: every scan is done once Gazelle resolved the
// dependencies.
func (l *godotLang) AfterResolvingDeps(context.Context) {
	if l.scanner != nil {
		l.scanner.stop()
		l.scanner = nil
	}
}
