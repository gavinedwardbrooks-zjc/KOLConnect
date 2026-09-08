# TikTok Passive Capture V2 (Post-M8)

The historical M3.1 pipeline was retired during PRE-M8. M8.3-T now reuses its parser,
sanitized fixtures and wrappers as a runtime acceptance candidate, wired into the extension
at document_start (TikTok only). This is not evidence of real TikTok acceptance.

Passive TikTok network capture/import is not supported in the current release until real
browser E2E passes. TIKTOK_PRODUCTION_SUPPORT = NO; REAL_E2E_RESULT = NOT_RUN.

## Revalidation boundary

M8.3-T uses L1 post-item-list responses, then L2 embedded hydration and L3 visible DOM.
It makes no extra TikTok requests and adds no scrolling. The bridge allowlists at most 100
items per response; the MAIN replay buffer holds at most 10 envelopes; each isolated tab
session holds at most 200 video IDs. Preview/import is limited to 20 rows by the existing
application import contract. A reset clears the buffer and rejects in-flight old observations.

The bridge token is retrieved through extension messaging and MAIN scripting, not accepted
from a page bootstrap. Same-page scripts can still observe postMessage; it is not a guarantee
of platform truth. Payloads are untrusted, allowlisted, bounded and require explicit import.
Login/challenge/CAPTCHA pauses the session; the user resolves it normally and explicitly resets.
Unknown-profile/feed data is not imported. Hydration without author identity requires matching
visible profile video links. Missing values remain null and lower layers cannot override L1.

The existing import flow writes Creator/CreatorAccount and existing capture snapshot observations
to SQLite. Repeated imports converge on the account identity; distinct captures may retain separate
observations of a video. No automatic Campaign publication linkage or M8.4 tracking is added.

## Real acceptance checklist (pending)

Load the unpacked extension, refresh a TikTok profile and browse normally. Confirm naturally
initiated item-list requests appear as L1 preview rows, with no added extension requests; check
dedupe, metrics, provenance, reset and account navigation. Explicitly import into an isolated
KOLConnect test runtime, verify SQLite identity convergence, and check Instagram still works.
If a challenge appears, stop and resolve it manually, never bypass it. Retain sanitized evidence
of the network, preview and import results before changing the production support gate.
