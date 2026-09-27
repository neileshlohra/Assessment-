# Test Plan / Matrix

| Area | ID | Scenario | Expected | Priority | Automation |
|---|---|---|---|---|---|
| Sync | SYNC-01 | Two devices use same local ID | Both records preserved with distinct server IDs | P0 | Automated |
| Sync | SYNC-02 | Exact replay | Idempotent response; no duplicate | P0 | Automated |
| Sync | SYNC-03 | 50 concurrent replays | One create, remaining duplicates | P0 | Automated |
| Sync | SYNC-04 | 500/5000/50000-client load | Backend remains within agreed SLO/error budget | P0 | Load test |
| Sync | SYNC-05 | Network loss at 99% upload | Local data retained; retryable state | P0 | Manual + instrumentation |
| Sync | SYNC-06 | HTTP 500 | WorkManager retry; data retained | P0 | Instrumentation |
| Form | FORM-01 | Hobby=Yes | Hobby text visible | P0 | Automated |
| Form | FORM-02 | Hobby=No | Hobby text hidden | P0 | Automated |
| Form | FORM-03 | Toggle Yes/No repeatedly | UI converges correctly | P1 | Automated |
| Form | FORM-04 | All visibility operators | Correct visibility | P0 | Automated |
| Form | FORM-05 | 20+ input types | Renderer maps each type correctly | P0 | Automated |
| HFC | HFC-01 | Age<15 + College | Reask/flag | P0 | Automated |
| HFC | HFC-02 | Age=15 + College | No invalid match | P0 | Automated |
| HFC | HFC-03 | Sleep Yes + <6h | Reask/flag | P0 | Automated |
| HFC | HFC-04 | reask_once | No infinite loop | P0 | Automated |
| Android | AND-01 | Offline save | Room row persisted | P0 | Instrumentation |
| Android | AND-02 | App process death | Pending data survives | P0 | Instrumentation |
| Android | AND-03 | WorkManager retry | Backoff and eventual success | P0 | Instrumentation |
| Android | AND-04 | 4GB device + 4 videos | No ANR/crash under target conditions | P0 | Device test |
| UX | UX-01 | Bright sunlight | Content remains legible | P1 | Device/manual |
| UX | UX-02 | Small screen | No clipping/hidden CTA | P1 | Device/manual |
| UX | UX-03 | Low literacy | Visual/audio cues understandable | P0 | Exploratory |
