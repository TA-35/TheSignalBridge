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

## Rao & Daumé Clarification Questions Dataset
- URL: https://go.umd.edu/clarification_questions_dataset
- Status: DEAD LINK as of 2026-08-30 — confirmed "Sorry, the file you have requested does not exist" on Google Drive
- Decision: Not used for Iteration 1. No current user story
  (US1.1-1.3, US2.1-2.3) requires clarification-question generation, so this gap does not block current scope.
- Possible substitute if needed later: ClarQ dataset
  (github.com/vaibhav4595/ClarQ), CC BY 4.0, ACL 2020 — link status and data shape not yet verified