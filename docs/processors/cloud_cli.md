# Cloud CLI Processor

**File:** `src/processors/cloud_cli.py` | **Priority:** 39 | **Name:** `cloud_cli`

Handles cloud provider CLI output.

## Supported Commands

aws, gcloud, az (Azure CLI).

## Strategy

| Format | Strategy |
|---|---|
| JSON output (describe/list) | Recursively compresses nested JSON: truncates at depth 4, collapses arrays > 5 items to first 3 + count. Preserves all error/status/state/name/id/arn/type/tag fields at full depth |
| Table output (`--output table`) | Keeps header + first 15 and last 5 rows |
| Text/TSV output (`--output text`) | Keeps first 20 and last 10 lines |

## What is preserved

- Resource identifiers (IDs, ARNs, names)
- State/status information
- Error messages and codes
- Tag key-value pairs
- First and last items in large lists

## What is removed

- Deeply nested metadata beyond depth 4 (replaced with `{... N keys}`)
- Middle items in large arrays (replaced with `... (N more items)`)
- Long string values truncated at 200 characters
- Middle rows in large tables

## Example

**Before** (aws ec2 describe-instances, 648 lines):
```json
{
  "Reservations": [
    {
      "Instances": [
        {
          "InstanceId": "i-0abc123",
          "State": {"Name": "running"},
          "Tags": [{"Key": "Name", "Value": "prod-web"}],
          "SecurityGroups": [... 10 items],
          ...
        }
      ]
    }
  ]
}
```

**After** (16 lines):
```json
{
  "Reservations": [
    {
      "Instances": [
        {
          "InstanceId": "i-0abc123",
          "State": {"Name": "running"},
          "Tags": [{"Key": "Name", "Value": "prod-web"}],
          "SecurityGroups": "[... 10 items]"
        }
      ]
    }
  ]
}
```
