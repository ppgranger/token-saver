# Build Output Processor

**File:** `src/processors/build_output.py` | **Priority:** 25 | **Name:** `build`

Handles build tool output across all major ecosystems.

## Supported Commands

npm/yarn/pnpm (run/install/build/ci/audit), cargo build/check, make, cmake, gradle, mvn, ant, pip install, poetry install/update, uv pip/sync, tsc, webpack, vite, esbuild, rollup, next build, nuxt build, turbo run/build, nx run/build, bazel build, sbt, mix compile, docker build, docker compose build.

## Strategy

| Outcome | Strategy |
|---|---|
| **Success** | `Build succeeded.` + size/timing lines if present + warning count |
| **Error** | All error messages preserved with context (stack traces, code pointers, `~~`/`^^` markers). Tolerates single blank lines between TypeScript/multi-file errors |
| **Docker build** | Keeps step headers (`Step N/M`, `#N`, `[N/M]`) and final result, strips intermediate containers, SHA hashes, and layer downloads |
| **npm audit** | Groups vulnerabilities by severity (critical/high/moderate/low) with package names. Shows fix recommendations |

## Exclusions

- `pip list`/`pip freeze`/`npm ls`/`npm list`/`conda list` are routed to `PackageListProcessor`
- `cargo clippy` is routed to `LintOutputProcessor`

## Removed Noise

Progress bars, installation lines, spinners, download counters, pip progress bars, `[1/5]` progress indicators, cargo `Compiling` lines, `Already up to date`, `Using cached`, `Collecting` lines, yarn berry resolution/fetch/link steps, pnpm resolved/reused stats.
