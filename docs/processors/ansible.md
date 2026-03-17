# Ansible Processor

**File:** `src/processors/ansible.py` | **Priority:** 40 | **Name:** `ansible`

Handles `ansible-playbook` and `ansible` command output.

## Supported Commands

| Command | Strategy |
|---|---|
| `ansible-playbook` | Keeps PLAY/TASK headers, changed/failed/fatal lines, PLAY RECAP. Counts and summarizes ok/skipped tasks |
| `ansible` (ad-hoc) | Same strategy |

## Compression Strategy

- **Always preserved:** PLAY and TASK headers, changed/failed/fatal/unreachable lines, error messages (`msg:`), full PLAY RECAP section
- **Compressed:** ok tasks (counted), skipping tasks (counted), separator lines (`****`), included/imported lines
- **Summary:** Inserted at top, e.g. `[42 ok, 3 skipped]`
- **Threshold:** Output with 20 or fewer lines passes through unchanged
