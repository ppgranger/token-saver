# Helm Processor

**File:** `src/processors/helm.py` | **Priority:** 41 | **Name:** `helm`

Handles Helm CLI output for chart management operations.

## Supported Commands

| Command | Strategy |
|---|---|
| `helm template` | Summarizes YAML manifests: counts manifests and total lines, lists each Kind/Name with line count |
| `helm install` | Keeps status lines, omits NOTES section boilerplate |
| `helm upgrade` | Same as install |
| `helm status` | Same as install |
| `helm list` | Keeps header + first 19 releases, truncates remainder with count |
| `helm history` | Keeps header + last 10 revisions, truncates older with count |
| `helm rollback` | Passes through (typically short) |
| `helm uninstall` | Passes through (typically short) |
| `helm get` | Passes through |

## Thresholds

- `helm template`: 50 lines before summarization
- `helm install/upgrade/status`: 20 lines before NOTES omission
- `helm list`: 25 lines before truncation
- `helm history`: 15 lines before truncation
