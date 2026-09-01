# Source Dataset Registry

## Enron Email Dataset
- URL: https://www.cs.cmu.edu/~enron/
- License: Non-commercial research use only
- Downloaded: 2026-08-30
- Owner: Amulya Reddy
- Note: the roadmap flagged heavy duplication as expected (same email in
  sender's Sent + every recipient's Inbox). Verified directly against the
  full 517,401-row parsed dataset - Message-IDs are 100% unique, zero
  duplicates found by ID or by content hash. This particular CMU-hosted
  release of the corpus does not exhibit the duplication pattern often
  associated with the original FERC dataset. Confirmed via direct check,
  not assumed.

- PII masking limitation: email addresses and phone numbers are reliably masked via regex, and sender/recipient fields are pseudonymised
  (Person_1, Person_2, ...). However, full names mentioned casually in the body or subject text (e.g. "dinner with Louise and John") are NOT caught - there's no reliable regex pattern for detecting names. Spot- checked and confirmed this gap exists in the cleaned output. If names-in-text needs to be addressed before annotation, a named-entity- recognition step would need to be added as a follow-up.

 - Thread reconstruction: In-Reply-To and References headers are both 0% populated in this dataset (confirmed by direct check, not assumed) - proper header-based reply-chain threading isn't possible here.Threads are grouped instead by normalised subject + sender within a  7-day window. Known limitation: this can't catch a reply that doesn't share the same subject line, and could occasionally merge unrelated messages that coincidentally share both subject and sender within the window. 196,286 distinct threads identified across 455,514 messages.

- Data quality fixes found via spot-checking (not caught by "0 errors" parse/clean summaries alone): forwarded-message markers ("Forwarded by X on date") were leaking into cleaned_text due to a
  regex missing re.DOTALL; CALENDAR ENTRY exports and HourAheadmschedule-alert system messages were not being filtered as automated mail. All three fixed and verified. Final cleaned row count: 455,514. 

## Rao & Daumé Clarification Questions Dataset
- URL: https://go.umd.edu/clarification_questions_dataset
- Status: DEAD LINK as of 2026-08-30 — confirmed "Sorry, the file you have requested does not exist" on Google Drive
- Decision: Not used for Iteration 1. No current user story
  (US1.1-1.3, US2.1-2.3) requires clarification-question generation, so this gap does not block current scope.
- Possible substitute if needed later: ClarQ dataset
  (github.com/vaibhav4595/ClarQ), CC BY 4.0, ACL 2020 — link status and data shape not yet verified


  ## Annotation Sample v1
- Source: 455,514 cleaned Enron messages (post dedup/automated-mail
  removal/length filter/PII masking)
- Method: stratified by message length (short/medium/long) and a rough
  ambiguity heuristic (question marks, hedging language, very short
  text), capped at 2 messages per thread to avoid over-representing
  long back-and-forth threads
- Sample size: 400 messages, random seed 42 (reproducible)
- Sender diversity: 279 unique senders represented
- Full breakdown recorded in data/staging/annotation_sample_v1_manifest.txt
  (not committed - gitignored along with other staging data)