# Maven/Gradle Processor

**File:** `src/processors/maven_gradle.py` | **Priority:** 28 | **Name:** `maven_gradle`

Dedicated processor for Maven and Gradle build output.

## Supported Commands

mvn, ./mvnw, gradle, ./gradlew (all subcommands).

## Strategy

### Maven

| Output Type | Strategy |
|---|---|
| **Download lines** | Strip `[INFO] Downloading from` and `[INFO] Downloaded from` lines. Show count |
| **Module lines** | Count `[INFO] Building module-name` lines |
| **Errors** | Keep all `[ERROR]` and `[FATAL]` lines |
| **Warnings** | Keep first 5 `[WARNING]` lines, summarize rest |
| **Test results** | Keep `Tests run: N, Failures: N` lines |
| **Reactor summary** | Keep reactor summary block |
| **Build result** | Keep `BUILD SUCCESS`/`BUILD FAILURE` and timing |

### Gradle

| Output Type | Strategy |
|---|---|
| **Task lines** | Strip `UP-TO-DATE`, `NO-SOURCE`, `SKIPPED`, `FROM-CACHE` tasks. Keep executed tasks. Show counts |
| **Errors** | Keep `FAILURE:` blocks, error details, `What went wrong` sections |
| **Test results** | Keep test result summary lines |
| **Build result** | Keep `BUILD SUCCESSFUL`/`BUILD FAILED` and actionable task summary |

## Configuration

No dedicated configuration keys. Uses default compression thresholds.

## Removed Noise

Maven: `[INFO] Downloading/Downloaded` lines, separator lines (`-----`), empty `[INFO]` lines. Gradle: `UP-TO-DATE`/`NO-SOURCE` task lines, progress indicators.
