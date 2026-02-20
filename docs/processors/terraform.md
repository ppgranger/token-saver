# Terraform Processor

**File:** `src/processors/terraform.py` | **Priority:** 33 | **Name:** `terraform`

Handles Terraform and OpenTofu commands.

## Supported Commands

| Command | Strategy |
|---|---|
| `terraform plan` / `tofu plan` | Strips provider initialization and backend configuration. For create (+): keeps all attributes. For update (~): keeps only changed attributes (with `->`). For destroy (-): keeps resource header only. Always preserves: Plan summary, errors, warnings, output changes, `(known after apply)`, `forces replacement` |
| `terraform apply` / `tofu apply` | Same as plan, plus Apply/Destroy complete messages |
| `terraform destroy` / `tofu destroy` | Same as plan |
| `terraform init` / `tofu init` | Strips verbose initialization messages (Initializing, Finding, Installing, etc.). Keeps provider versions, success message, errors, warnings, upgrade notices. Short output (< 20 lines) passes through |
| `terraform output` / `tofu output` | Truncates very long output values (> 200 chars) with char count. Short output (< 30 lines) passes through |
| `terraform state list` / `tofu state list` | Groups resources by type with counts. Short output (< 30 lines) passes through |
| `terraform state show` / `tofu state show` | Truncates long attribute values (> 200 chars). Truncates output > 80 lines |

## Subcommand Detection

Uses a compiled regex to extract the exact subcommand from the command string, preventing false matches when subcommand names appear as argument values (e.g., `terraform plan -var init=true` correctly routes to the plan handler, not init).
