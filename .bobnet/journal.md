# Bobnet journal

## 2026-10-07 12:13 — v0.3.0: Charles → infrastructure, Sandbox-Bob → canary
- Did: new `agents/charles.md` (Terraform/Azure/AWS/IAM, plans-never-applies) + `commands/terraplan.md`; canary renamed `charles` → `sandbox-bob`; Busters gains apply/state-surgery/privilege-grant ASK patterns and heredoc-body downgrade (KILL→ASK); Autofactory lints only when project has linter config, no more npx. Commit 2ebe72b, pushed.
- Decided: privilege grants weigh the same as deletes in Busters (DevSecOps rationale); linters need project opt-in, formatters don't — stops global rule sets being imposed. Sandbox-Bob chosen over Arthur for the canary (air-gapped lore fits a canary that reports back).
- Open: `v0.2.0`/`v0.3.0` tags not pushed — session git proxy drops tag refs; push from a local clone. Installed plugin in this session is the claude.ai-synced 0.2.0 copy, so old hooks still fire until Chloe re-syncs. README still needs a Busters screenshot/GIF.
- Bobs: solo
