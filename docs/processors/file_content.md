# File Content Processor

**File:** `src/processors/file_content.py` | **Priority:** 51 | **Name:** `file_content`

Content-aware compression for file viewing commands. Instead of blind head/tail truncation, detects content type and applies a specialized strategy.

## Supported Commands

cat, head, tail, bat, less, more.

## Content Type Detection

| Content Type | Detection | Strategy |
|---|---|---|
| **Code** | Extension: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.go`, `.rs`, `.java`, `.kt`, `.c`, `.cpp`, `.h`, `.hpp`, `.rb`, `.php`, `.swift`, `.scala`, `.tf`, `.hcl`, `.sh`, `.bash`, `.zsh`, `.ps1`, `.lua`, `.r`, `.m`, `.cs`, `.vb`, `.pl`, `.pm`, `.ex`, `.exs`, `.hs`, `.ml`, `.vue`, `.svelte`, `.dart`, `.zig`, `.nim`, `.v`, `.groovy`, `.sql`, `.md`, `.rst` | Keeps imports/headers (first 20 lines), function/class/method signatures + 3 body lines, TODO/FIXME/HACK/BUG/XXX markers. Summary: `(N total lines, M definitions found, K lines omitted)` |
| **Config** | Extension: `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.xml`, `.env`, `.properties`, `.plist`, `.conf` | JSON: parsed structure with top-level keys, truncated arrays/strings. YAML: keeps indent <= 2 lines. XML: keeps indent <= 4 lines. INI/TOML/CFG: keeps section headers and key=value lines |
| **Logs** | Extension or heuristic (> 30% lines match timestamp/log-level patterns) | Keeps first 5 + last 5 lines (temporal context), ERROR/WARN/FATAL with +/- 2 context lines, counts INFO/DEBUG lines |
| **CSV/TSV** | Extension (`.csv`, `.tsv`) or heuristic (consistent separators) | Header + 5 first data rows + 3 last rows + `(N data rows, M columns)` |
| **Unknown** | Fallback | Head/tail truncation: first 150 + last 50 lines |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `max_file_lines` | 300 | Threshold before compression kicks in |
| `file_keep_head` | 150 | Lines from start (fallback strategy) |
| `file_keep_tail` | 50 | Lines from end (fallback strategy) |
| `file_code_head_lines` | 20 | Import/header lines for code files |
| `file_code_body_lines` | 3 | Body lines per definition |
| `file_log_context_lines` | 2 | Context lines around errors in logs |
| `file_csv_head_rows` | 5 | Data rows from start of CSV |
| `file_csv_tail_rows` | 3 | Data rows from end of CSV |

## Definition Detection

Recognizes function/class/method/interface/enum/trait/impl/struct signatures in: Python, JavaScript/TypeScript, Go, Rust, Java/Kotlin/C#, C/C++, Ruby, PHP, Shell.

The C/C++ pattern requires a return type keyword (void, int, char, float, double, bool, auto, size_t, std::*, struct/enum/class names, *_t types) to avoid false positives on any line containing parentheses.
