# QA Engineer Take-Home Assessment

## Overview

This submission covers the four parts of the QA assessment for an offline-first Android field-survey application and a dynamic web Survey Builder.

### Tooling choice

- **API:** Python + pytest + requests against a deterministic local mock sync service. This makes the duplicate-local-ID and idempotency behavior executable without requiring a real backend.
- **Web:** Playwright + TypeScript. The test uses a small schema-driven fixture that implements the supplied `visibilityLogic` contract, allowing the dynamic-form behavior to be verified without depending on an unavailable production UI.
- **Android investigation:** ADB, Android Studio Profiler, `dumpsys`, WorkManager diagnostics, Room inspection, and Charles Proxy/Proxyman.
- **CI:** GitHub Actions can run the API and web suites on every pull request.

The important QA principle throughout is: **local IDs are device-local and must never be treated as globally unique server identifiers.** Server identity should be based on a globally unique survey/record UUID, while `(device_id, local_id)` can be retained as an idempotency/deduplication key.

---

# Part 1 — Hands-on Technical Inspection & Automation

## Scenario A — Offline Sync & Data Collision

### Expected contract

A sync payload should contain at least:

```json
{
  "deviceId": "device-ankit-01",
  "localId": "School_1",
  "surveyId": "uuid-generated-on-device",
  "schemaVersion": 3,
  "payload": { "schoolName": "Govt Primary School" },
  "clientUpdatedAt": "2026-09-26T17:00:00Z"
}
```

The server should:

1. Accept the first record.
2. Treat a repeated request with the **same `deviceId + localId + surveyId`** as idempotent rather than creating another record.
3. Accept another worker's `School_1` because the local ID is not globally unique.
4. Never overwrite Ankit's record with Pooja's record merely because both have `localId = School_1`.
5. Return a deterministic response such as `201 created` for a new record and `200 duplicate/idempotent` for a replay.
6. Prefer an idempotency key or globally unique survey UUID for transport-level deduplication.

### Automation

See `api-tests/test_sync_api.py`.

The suite covers:

- two devices using the same local ID;
- replaying the exact same payload;
- concurrent submissions;
- payload identity checks to detect accidental overwrites;
- invalid payload handling;
- a simple burst/concurrency simulation.

### Backend-load/DDoS mitigation strategy

For 50,000 clients reconnecting together, I would not make every device independently hammer the API. I would use:

- WorkManager constraints for network availability;
- randomized initial delay/jitter;
- exponential backoff with a cap;
- bounded batch size;
- server-side rate limiting;
- idempotency keys;
- pagination/chunked uploads;
- compressed request bodies where practical;
- a queue/ingestion layer if volume requires it;
- metrics for request rate, queue depth, retry rate, 4xx/5xx, and sync latency.

I would explicitly test a **thundering-herd** condition with progressively larger virtual-device counts rather than assuming a single-device test predicts production behavior.

### Android background-sync test under a poor network

**Tools:** ADB, Android Studio Profiler, Charles Proxy or Proxyman, `adb shell dumpsys`, and Android network controls.

Test flow:

1. Create and save a survey completely offline.
2. Start a photo upload.
3. Throttle the connection and introduce latency.
4. At approximately 99% completion, cut the connection.
5. Verify the local Room record remains present and is still marked pending.
6. Verify the partial file is either safely resumable or safely discarded and re-uploaded; no corrupt attachment should be marked synced.
7. Restore connectivity.
8. Verify WorkManager retries with backoff and the record eventually becomes synced exactly once.
9. Kill/restart the app during retry and verify the work remains recoverable.
10. Repeat with airplane mode, process death, low storage, and a 500 response.

I would capture request/response logs, WorkManager state, Room state, file checksum/size, and server-side IDs for every run.

---

## Scenario B — Dynamic Form Rendering & Regression

### Web automation

See `web-tests/tests/visibility.spec.ts` and `web-tests/fixtures/hobby-form.html`.

The test validates the supplied schema behavior:

- `q_3 = No` → `q_4` is hidden.
- `q_3 = Yes` → `q_4` becomes visible.
- changing back to `No` hides `q_4` again.
- hidden conditional fields are not accidentally submitted.

### Dynamic-schema regression strategy

I would split the regression suite into four layers:

| Layer | What to automate | Why |
|---|---|---|
| Schema contract | JSON schema validation, required fields, supported input types, version compatibility | Fast detection of malformed schemas |
| Renderer contract | Every supported input type, required/read-only/hidden behavior, validation | Protects the schema-to-UI engine |
| Logic engine | `equals`, `not_equals`, `contains`, numeric comparisons, empty/not-empty, AND/OR HFC | High-risk business behavior |
| End-to-end journeys | Representative real forms on Android/web | Detects integration failures |

### Combinatorial test approach

I would not manually create every possible combination of 20+ input types and rules. Instead I would generate schemas from a test-data matrix covering:

- each input type at least once;
- each visibility operator;
- true/false/null/empty values;
- required vs optional;
- validation boundaries;
- nested roster forms;
- translated labels;
- schema version upgrades;
- media/attachment references;
- HFC `all` and `any` combinations.

Then use a smaller set of end-to-end "golden forms" representing realistic business workflows.

### Manual exploratory testing

I would keep these primarily manual:

- first-use usability;
- confusing question wording;
- low-literacy visual comprehension;
- sunlight/readability;
- touch ergonomics;
- unusual field-worker workflows;
- accessibility with real users/devices;
- exploratory interruption/recovery flows that are difficult to exhaustively model.

Automation proves repeatable behavior; exploratory testing finds unexpected behavior.

---

## Scenario C — Offline Sync, Room & WorkManager

### 1. Inspect Room database on an unrooted test device

Preferred approach depends on the build configuration.

**If the debug build is debuggable:**

1. Install the APK on a dedicated test device/emulator.
2. Enable USB debugging.
3. Reproduce: airplane mode → create survey → save.
4. Use Android Studio **App Inspection → Database Inspector** for the debuggable application.
5. Query the relevant Room tables and verify:
   - survey UUID;
   - local/device ID;
   - answers;
   - sync state = pending;
   - timestamps;
   - attachment metadata.
6. Export/capture the relevant rows as test evidence.

Example ADB checks:

```bash
adb devices
adb shell dumpsys package <package.name>
adb shell run-as <package.name> ls -la databases/
adb shell run-as <package.name> ls -la files/
```

`run-as` works only when the installed package/build permits it. On a production non-debuggable APK, direct private-database access is intentionally restricted on an unrooted device. In that case I would use an instrumented/debug build, a QA-only diagnostic screen/export, or Android Studio inspection on a debuggable variant rather than attempting to bypass Android security.

### 2. Force WorkManager for testing

For modern WorkManager, I would make the sync worker testable by exposing a QA/debug trigger or using WorkManager's test APIs in instrumentation tests. I would **not** depend on an undocumented production ADB command as the primary test method.

Useful observation commands include:

```bash
adb shell dumpsys jobscheduler
adb shell dumpsys activity services
adb logcat | grep -i -E "WorkManager|SyncWorker|WM-"
```

For deterministic instrumentation tests, use `WorkManagerTestInitHelper`, `TestDriver`, and a controlled executor to mark constraints as met and advance the worker.

### 3. Simulate HTTP 500 and verify retry

Using Charles/Proxyman:

1. Configure the test device to use the proxy.
2. Trust the proxy certificate only on the QA/debug build where permitted.
3. Match `POST /sync-survey`.
4. Override the response to `500`.
5. Trigger sync.
6. Verify the API call returns 500.
7. Verify the Room row remains `PENDING` (or an equivalent retryable state).
8. Verify the attachment remains available.
9. Verify WorkManager reports a retry/backoff state rather than success.
10. Restore the real server response.
11. Allow retry and verify one successful server record.
12. Verify the local row transitions to `SYNCED` only after success.

The key invariant is: **a network failure must never cause local data to be deleted or falsely marked synced.**

---

# Part 2 — Complex Scenarios & Edge Cases

## Scenario D — 4 GB device / training-video crash

### Reproduction

Use a physical 4 GB RAM device or Android emulator configured to approximate the field device.

Baseline the device first:

```bash
adb shell free -m
adb shell dumpsys meminfo <package.name>
adb shell df -h
adb shell dumpsys cpuinfo
```

Then:

1. Fresh-install the app.
2. Record baseline memory/storage.
3. Open video 1, play to completion, return to dashboard.
4. Open video 2, complete it.
5. Open video 3, complete it.
6. Open video 4.
7. Repeat navigation between modules.
8. Rotate/recreate the activity if supported.
9. Background/foreground the app between videos.
10. Capture the first point where frame rate, memory, or responsiveness changes.
11. Repeat three times to distinguish deterministic leakage from a one-off failure.

### Low-memory manipulation

For an emulator, configure a small RAM profile in AVD settings. On a controlled test device/emulator, also use memory-pressure testing techniques and background applications to reduce available memory. Do not treat `ulimit` as an Android-app memory model; use Android's actual memory-management tools and profiler data.

### Low-storage manipulation

Create a controlled low-storage condition using large disposable test files on the test device, then verify with:

```bash
adb shell df -h /data
adb shell du -h /data/local/tmp
```

Keep a known recovery margin so the device does not become unusable.

### Debugging/proof

Use Android Studio Profiler to capture:

- Java/Kotlin heap;
- native memory where relevant;
- allocations over repeated video transitions;
- CPU;
- network;
- frame rendering.

Also capture:

```bash
adb logcat -v threadtime > anr-log.txt
adb shell dumpsys meminfo <package.name> > meminfo.txt
adb shell dumpsys activity processes > processes.txt
```

For an ANR, look for the generated ANR traces on supported test configurations and correlate the main-thread stack with profiler data. I would compare memory after each module. If memory rises monotonically and is not reclaimed after leaving the video screen, then reproduce with a heap dump and identify retained `Activity`, `Fragment`, bitmap, player, or media-buffer references.

### Developer-facing root-cause evidence

A useful bug report contains:

- exact device model, Android version, RAM/storage;
- APK build/version;
- reproducibility rate;
- exact steps;
- screen recording;
- logcat/ANR trace;
- profiler capture;
- memory before/after each video;
- whether process restart clears the symptom;
- suspected retained object and allocation evidence.

That changes "it crashes on cheap phones" into a measurable engineering defect.

---

## Scenario E — HFC Engine Test Plan

| ID | Scenario | Input | Expected |
|---|---|---|---|
| HFC-01 | Age below minimum | Age=14, Education=College | Rule matches; re-ask and flag according to configured action |
| HFC-02 | Age boundary | Age=15, Education=College | No `<15` match |
| HFC-03 | Age above boundary | Age=16, Education=College | No `<15` match |
| HFC-04 | Education changes | Age=14, Education=School | No match if both conditions are required |
| HFC-05 | Sleep contradiction | Sleep Well=Yes, Sleep hours=5 | Re-ask/flag |
| HFC-06 | Sleep boundary | Sleep Well=Yes, Sleep hours=6 | No `<6` match |
| HFC-07 | Sleep well = No | Sleep Well=No, hours=5 | Rule requiring Yes does not fire |
| HFC-08 | Missing dependency | Sleep Well unset | Rule must not crash; wait until required attributes exist |
| HFC-09 | Invalid numeric value | Sleep hours=`abc` | Numeric validation handles it; HFC must not corrupt state |
| HFC-10 | OR logic | One of two invalid conditions true | `any` rule fires |
| HFC-11 | AND logic | Only one condition true | `all` rule does not fire |
| HFC-12 | Re-ask once | Same invalid answer entered twice | Second response is accepted/flagged when action is `reask_once`; no infinite loop |
| HFC-13 | Corrected value | Invalid → user corrects value | Rule clears or does not re-trigger for the corrected state |
| HFC-14 | Rapid edits | User changes dependency repeatedly | Engine converges to final state without duplicate prompts |
| HFC-15 | Roster isolation | Invalid answer in roster row 1 | Row 2 is not incorrectly flagged |
| HFC-16 | Rule versioning | Old schema vs new schema | Correct rule set executes for schema version |

### Infinite-loop guard

Every re-ask rule needs state such as `ruleId + record/roster-row + occurrence`. For `reask_once`, the engine should persist that it has already prompted once. The rule must not fire repeatedly because the UI re-rendered.

---

# Part 3 — QA Process & AI Integration

## First 30 days

### Days 1–5: Understand and baseline

- Map release flow, environments, APIs, mobile builds, and ownership.
- Review current defects, Play Store release history, crash/ANR data, and support issues.
- Build a risk map for offline sync, schema rendering, data integrity, and training.
- Establish a shared defect template and severity definitions.
- Define a minimum smoke suite.

### Days 6–10: Establish test foundations

- Create QA/staging environment expectations.
- Define entry criteria: build installs, critical dependencies available, schema version identified, smoke prerequisites satisfied.
- Define exit criteria: critical/high defects resolved or explicitly accepted, smoke/regression pass, sync/data-integrity checks pass, release evidence attached.
- Add API and schema-contract tests to CI.
- Establish a small device matrix: representative 4 GB Android device, current Android version, low-storage scenario, poor-network scenario.

### Days 11–20: Automation and release gates

- Automate stable, high-risk flows.
- Add dynamic-schema contract tests.
- Add API idempotency and retry tests.
- Add Android instrumentation tests for Room/WorkManager behavior.
- Run smoke tests on every candidate build.
- Run broader regression nightly or before release.

### Days 21–30: Make the process sustainable

- Add dashboards for pass rate, escaped defects, flaky tests, crash/ANR rate, sync failures, and release lead time.
- Review flaky tests and remove low-value automation.
- Introduce a lightweight bug triage/release checklist.
- Pair with developers on unit/integration test coverage.
- Run a retrospective and tune the process based on actual bottlenecks.

### Avoiding QA as a bottleneck

QA should not become a manual approval queue. The process should push fast feedback left:

`PR → unit/schema/API checks → build → automated smoke → QA exploratory/risk testing → release candidate → release evidence`.

Developers remain responsible for unit/integration quality; QA owns risk-based system validation, test strategy, release confidence, and independent exploratory testing.

## AI in day-to-day QA

I use AI as an accelerator, not as the source of truth. Typical uses include:

- turning acceptance criteria into candidate test scenarios;
- generating boundary-value and negative-data combinations;
- reviewing automation for missing assertions;
- generating test-data variations from JSON schemas;
- explaining logs and stack traces;
- creating SQL/API payload variants;
- summarizing repeated defect patterns;
- drafting regression checklists.

### Specific dynamic-schema example

Given a schema containing 20 input types and visibility rules, I can provide the schema to an AI tool and ask it to generate a test matrix containing:

```text
questionId
inputType
visibility operator
expected visible state
boundary values
required/optional state
validation cases
HFC dependencies
```

I would then review the generated matrix against the actual product specification and convert the stable cases into automated tests. AI-generated assertions are not accepted blindly; the schema/specification remains the source of truth.

## Automation decision framework

Automate when the test is:

- repeated frequently;
- deterministic;
- business-critical;
- expensive to execute manually;
- data-heavy;
- easy to assert objectively.

Prefer manual/exploratory testing when the test is:

- usability-oriented;
- visual/qualitative;
- rapidly changing;
- highly exploratory;
- a one-off investigation.

The chosen tools reflect the assignment: Playwright gives reliable browser automation for generated forms, while Python/pytest gives a lightweight, readable API test harness that can run in CI without a full backend environment.

---

# Part 4 — UI/UX & User-Centric QA

## Training Video Hub evaluation

Functional correctness is only one dimension. For this user population I would test comprehension, visibility, touchability, performance, and recovery.

### UX/UI risks to flag

1. **Three dense paragraphs:** low-literacy users may not understand or read them. Replace with short phrases, icons, illustrations, or audio where appropriate.
2. **Small/standard Next button:** touch target may be too small or hard to hit accurately on budget phones.
3. **Next button at the bottom of a long page:** users may not discover it or may lose their place after scrolling.
4. **Low contrast:** bright sunlight can make text, controls, and video status difficult to see.
5. **Video thumbnail/player readability:** controls and progress indicators may be too small.
6. **Color-only feedback:** green/red should not be the sole signal; add icons/text/audio because color perception and sunlight vary.
7. **Memory/storage pressure:** video playback can cause memory spikes or consume scarce storage on 4 GB devices.
8. **Network recovery:** video start/pause/retry states must be clear when connectivity drops.
9. **Loading ambiguity:** a spinner without explanatory feedback can look like a frozen app.
10. **Orientation/layout issues:** small screens may clip content or push important actions below the fold.

### Systematic test method

Test on a representative device matrix:

- 4 GB RAM budget Android device;
- small display;
- bright outdoor/simulated sunlight;
- large system font/accessibility settings;
- low storage;
- 2G/poor Wi-Fi/airplane-mode transitions.

For each screen, verify:

- minimum practical touch target size;
- contrast and text legibility;
- no clipped/truncated content;
- clear focus/selection state;
- understandable icon + text pairing;
- scroll position preservation;
- video loading/error/retry behavior;
- memory/CPU impact over repeated module playback.

Where possible, involve actual representative users or field-worker feedback for comprehension rather than assuming that a technically accessible UI is understandable.

### Constructive defect communication

I would avoid subjective wording such as "bad UI." A good non-functional defect states:

**Title:** Next action is difficult to discover and tap on 5-inch budget device.

**Observed:** On the 4 GB test device at 100% display scale, the Next button is below three paragraphs and requires a long scroll. The target is difficult to hit accurately and is partially obscured when the keyboard/system UI is present.

**Expected:** Primary progression action remains clearly discoverable and comfortably tappable without accidental taps.

**Impact:** Increased completion time and risk of field-worker abandonment/data collection errors.

**Evidence:** Device/OS, screen recording, screenshots, reproduction rate, and accessibility/display settings.

This gives design and development an actionable problem, measurable impact, and evidence rather than an aesthetic opinion.

---

# Suggested CI commands

```bash
# API
python -m pip install -r api-tests/requirements.txt
pytest -q api-tests

# Web
cd web-tests
npm ci
npx playwright install --with-deps chromium
npx playwright test
```

# Acceptance checklist

- [x] Offline duplicate local-ID behavior covered.
- [x] API automation included.
- [x] Dynamic visibility automation included.
- [x] Android Room/WorkManager inspection strategy included.
- [x] Poor-network and 500-retry scenarios included.
- [x] Low-memory/low-storage investigation included.
- [x] HFC positive, negative, boundary and loop-prevention tests included.
- [x] 30-day QA process included.
- [x] AI integration described with a concrete schema example.
- [x] UX/non-functional field-user risks and test method included.
