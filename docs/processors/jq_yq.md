# JQ/YQ Processor

**File:** `src/processors/jq_yq.py` | **Priority:** 44 | **Name:** `jq_yq`

Compresses large JSON and YAML outputs from jq and yq.

## Supported Commands

jq, yq.

## Strategy

| Output Type | Strategy |
|---|---|
| **Small output** (< 50 lines) | Pass through unchanged |
| **jq JSON** | Parse as JSON, compress with `compress_json_value()` (truncate arrays > 5 items, summarize deeply nested objects). Re-serialize with indent |
| **jq streaming** (one JSON per line) | Detect repeated structure (same keys), show first 3 + count. Fallback to head/tail |
| **yq YAML** | Count top-level keys and list items. Collapse large arrays (> 3 items at same indent) to count. Add structure summary header |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| jq_passthrough_threshold | 50 | Lines below which output passes through unchanged |

## Notes

- No runtime dependencies: JSON parsing uses stdlib `json` module, YAML uses heuristic analysis (no PyYAML dependency)
- Streaming jq output (one value per line) is detected and compressed separately from single-document output
