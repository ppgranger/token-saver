# Go Processor

**File:** `src/processors/go.py` | **Priority:** 23 | **Name:** `go`

Dedicated processor for Go toolchain commands.

## Supported Commands

go build, go vet, go mod tidy, go mod download, go generate, go install.

## Strategy

| Subcommand | Strategy |
|---|---|
| **build/install** | Keep all `file.go:line:col: message` errors. For multi-package builds with many `# package` headers, truncate to first 3. Pass through unchanged if no errors (successful builds produce no output) |
| **vet** | Group warnings by type (printf, unreachable, shadow, unused, nil, loop). Show first N examples per type. Keep `# package` headers for context |
| **mod tidy/download** | Collapse `go: downloading X v1.0` lines into count. Keep `go: added/upgraded/downgraded/removed` lines (important dependency changes) |
| **generate** | Collapse `running` lines into count. Keep errors and generator output |

## Exclusions

- `go test` is routed to `TestOutputProcessor`
- `golangci-lint` is routed to `LintOutputProcessor`

## Configuration

Uses existing parameters:

| Parameter | Default | Description |
|---|---|---|
| lint_example_count | 2 | Examples per warning type (go vet) |
| lint_group_threshold | 3 | Minimum occurrences before grouping |

## Removed Noise

`go: downloading X` lines, `# package` headers (when redundant), `running` lines from go generate.
