---
title: Optional Markdown Section Workflow
description: Evaluate an opt-in Texio recipe against targeted reads and Token-Saver compression, with a disposable fixture and explicit measurement limits.
permalink: /markdown-workflow/
nav_order: 10
---

# Evaluate named Markdown sections

For a task confined to one Markdown heading, selecting that section can make
the relevant source easier to inspect. [Texio](https://github.com/Allra-Fintech/texio)
is an optional, separately installed companion for this workflow. Token-Saver
does not install it, invoke it, or rewrite file reads to use it. Compression
continues to use the Python standard library.

Use exact source when preparing an edit. Token-Saver's file-content processor
can shorten long Markdown output; its result is not a complete replacement
body. A named section also needs enough surrounding context to understand
cross-references and document-wide requirements.

## Try it on a disposable file

This POSIX-shell recipe uses **Texio 0.1.3**. Consult the upstream
[installation instructions and platform limits](https://github.com/Allra-Fintech/texio/blob/develop/docs/installation.md)
before installing it separately. The tested binary was extracted into a
temporary directory after checking its published SHA-256 checksum; no
Token-Saver installer or user profile was changed. Upstream describes Texio as
an early preview, so check the version when reproducing the trial.

```bash
texio --version
trial_dir=$(mktemp -d)
cat > "$trial_dir/README.md" <<'EOF'
# Demo

## Installation
Install the package.

### Requirements
Python 3.10 or later.
Keep this requirement when replacing the section.

## Usage
Keep this section unchanged.
EOF
cp "$trial_dir/README.md" "$trial_dir/before.md"
```

Inspect the headings, then read the complete selected section:

```bash
texio headings "$trial_dir/README.md" --json
texio section "$trial_dir/README.md" Installation
```

Replacement covers the whole selected body, including nested subsections.
Include the requirements you want to retain in the replacement file:

```bash
cat > "$trial_dir/installation.md" <<'EOF'
New installation instructions.

### Requirements
Python 3.10 or later.
Keep this requirement when replacing the section.

EOF
texio replace "$trial_dir/README.md" \
  --section Installation --from "$trial_dir/installation.md" --dry-run
cmp "$trial_dir/before.md" "$trial_dir/README.md"
```

The preview should change only `Install the package.` to
`New installation instructions.`. `cmp` should return status `0`, confirming
that the preview left the original bytes unchanged. Inspect the diff before
considering a write. See the upstream
[CLI contract](https://github.com/Allra-Fintech/texio/blob/develop/docs/cli-contract.md)
for explicit write modes and exit statuses.

## Compare against your existing reads

Run the following alternatives from the disposable directory. The fixed line
range is valid only for the fixture above; inspect the heading locations again
after changing it. `rg` here locates two known headings in this simple fixture,
not arbitrary Markdown section boundaries.

```bash
cd "$trial_dir"

# Whole captured file through Token-Saver
token-saver compress 'cat README.md' --exit-code 0 < README.md

# Targeted read with existing tools
rg -n '^## (Installation|Usage)$' README.md
sed -n '3,9p' README.md

# Named section with Texio
texio headings README.md --json
texio section README.md Installation
```

The `compress` command label is not executed: stdin supplies the already
captured file. Use an absolute path to `bin/token-saver` with Python 3.10+ if
the CLI is not on PATH.

The following small inspection trial was reproduced on Apple Silicon macOS
with Token-Saver **3.0.0**, its default configuration, Python **3.14.7**, and
Texio **0.1.3**. The fixture contains 174 ASCII characters. Counts sum each
command's stdout, including newlines, and the literal command strings above,
excluding setup (`cd`), comments, shell prompts and command separators.

| Workflow | Commands | Command characters | Stdout characters | Combined characters |
| --- | ---: | ---: | ---: | ---: |
| Whole captured file through Token-Saver | 1 | 62 | 174 | 236 |
| Targeted read with existing tools | 2 | 66 | 158 | 224 |
| Named section with Texio | 2 | 67 | 255 | 322 |

To reproduce the stdout counts, redirect each command to a separate file and
sum `wc -m` counts. The measurement redirections are instrumentation and are
excluded from the command-character counts above. These ASCII-only fixture
counts also equal byte counts. Custom Token-Saver configuration or a longer
document can change the compression result; this short file is unchanged with
the defaults.

Texio's heading discovery adds overhead on this small fixture. This trial
does **not** establish total task token savings. The combined counts omit
installation, instructions, tool-call envelopes, replacement generation,
preview/review, reasoning, retries, cached input and model tokenization.
They measure inspection only, not an end-to-end edit or billing.

The disposable-file checks also confirmed that the preview leaves the file
unchanged, the proposed replacement retains the nested requirements and the
adjacent Usage section, a missing heading returns status `4`, and duplicate
matching headings return status `5`. Those checks cover this fixture, not all
Markdown. Consult upstream's
[Markdown support limits](https://github.com/Allra-Fintech/texio/blob/develop/docs/markdown-support.md)
for dialect coverage and section-selection behavior.

## Decide using a complete task

Keep this as an opt-in recipe. Before adopting it for recurring work, compare
the same real task against your current targeted-read and editing workflow:

- Record tool versions, setup time and configuration, including any automatic
  output compression in the agent host.
- Count all discovery, read, edit and review calls, their arguments, stdout,
  stderr and retries. Include the generated replacement and diff review in
  both alternatives.
- Record actual input, output and cached tokens when the host provides them.
  If using character-based estimates, state the divisor and label them as
  estimates; keep setup costs separate from repeated-task costs.
- Verify the requested edit, retained nested content, unchanged surrounding
  sections and expected refusal for missing or ambiguous headings. Exercise
  real documents with fenced code and repeated headings.

Use the companion only if section selection improves your measured workflow
enough to justify its setup and command overhead. This evaluation adds no
automatic integration or measured model-token savings claim.
