# Kubernetes Processor

**File:** `src/processors/kubectl.py` | **Priority:** 32 | **Name:** `kubectl`

Handles kubectl and oc (OpenShift) commands. Supports global options (`-n`, `--namespace`, `--context`, `-A`, `--all-namespaces`, `--kubeconfig`).

## Supported Commands

| Command | Strategy |
|---|---|
| `kubectl get pods` | If all pods Running/Ready (N/N match): summarizes as count. Shows only unhealthy pods in detail |
| `kubectl get` (other resources) | Keeps header + data rows, truncates long outputs |
| `kubectl describe` | Strips noise sections (Tolerations, Volumes mounts, QoS Class, Annotations). Keeps: Name, Namespace, Node, Status, IP, container states, Conditions, Warning events |
| `kubectl logs` | Error-focused extraction: keeps first 10 + last 20 lines, error blocks with context |
| `kubectl top` | Passes through (already concise) |
| `kubectl apply` | Keeps result lines (created/configured/unchanged), errors, and warnings |
| `kubectl delete` | Keeps result lines (deleted), errors |
| `kubectl create` | Keeps result lines (created), errors |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `kubectl_keep_head` | 10 | Lines kept from start of logs |
| `kubectl_keep_tail` | 20 | Lines kept from end of logs |

## Multi-Container Ready Detection

The processor correctly detects multi-container pod readiness by comparing the numerator and denominator in the READY column as strings (e.g., `3/3` = ready, `2/3` = not ready, `10/10` = ready). This avoids the regex backreference limitation that would fail for numbers > 9.

## Describe Output Filtering

Uses exact set membership for kept keys (`key in keep_keys`) rather than substring matching, preventing false matches (e.g., "Namespace" would not accidentally match a key containing "space").
