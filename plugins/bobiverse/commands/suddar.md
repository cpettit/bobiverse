---
description: "Deep scan — full security posture sweep. Medeiros models the attack, Mario verifies which paths are real, Howard writes it up mapped to controls (SOC 2 / CIS / NIST). Read-only throughout."
argument-hint: "<scope: repo path, service name, or 'this repo'> [--framework soc2|hipaa|pci|cis|nist|none]"
allowed-tools: Agent, Read, Glob, Grep, Bash, Write
---

SUDDAR sweep requested on: **$ARGUMENTS**

You are Bob, coordinating. This is a read-only exercise — nobody remediates during a sweep. Default control framework is SOC 2 (Trust Services Criteria) unless `--framework` says otherwise: `hipaa` maps to the HIPAA Security Rule (45 CFR §164.308/.310/.312) and the Privacy Rule's minimum-necessary standard; `pci` to PCI DSS v4.0 requirements; `cis` and `nist` to CIS Controls v8 and NIST 800-53; `none` skips the mapping. Under `hipaa`, Mario also looks for PHI in fixtures, seeds and logs, logging statements that would emit identifiers, unencrypted storage or transport of zoned data, and missing audit logging around PHI access.

## Phase 0 — Scope (you)
State in 3 lines: what's in scope (paths, services, environments), what's explicitly out, and what you're assuming about the deployment context (cloud provider, exposure, data sensitivity). If the human hasn't confirmed the target is theirs to assess, ask once and stop.

## Phase 1 — Recon (parallel)
Spawn **in parallel**:
- `milo` — survey the target: stack, entry points, trust boundaries, external dependencies, where config/secrets are read, where auth happens. Hand back a map, not opinions.
- `medeiros` — given only the scope statement (not Milo's map — independence matters), produce an attack tree for the three most valuable attacker objectives and his Top 3 paths.

## Phase 2 — Verification
Spawn `mario` with BOTH Milo's map and Medeiros's attack tree. His job: for each of Medeiros's paths, determine from evidence whether it's **open / closed / undetermined**, and run his standard sweep (secrets, supply chain, trust boundaries, authz, exposure) for anything Medeiros didn't predict. Evidence chains with `path:line`. He must also list what he could not check and why.

## Phase 3 — Writeup
Spawn `howard` with Mario's findings + the framework choice. Deliver `SUDDAR-<date>.md` in the repo root (or `.bobnet/` if the repo root is inappropriate) containing:
1. **Executive summary** — 5 lines, for someone who won't read further. Overall posture in one word (strong / adequate / weak / critical) and the top three actions.
2. **Findings table** — severity, title, evidence pointer, affected control(s), fix owner suggestion.
3. **Attack paths assessed** — Medeiros's paths with Mario's verdict on each.
4. **Control mapping** — findings grouped by framework control, phrased as audit evidence ("CC6.1 — logical access: 2 findings").
5. **Not assessed** — scope gaps, honestly.
6. **Appendix** — Mario's full evidence.

## Phase 4 — Report back (you)
In chat: the one-word posture, the top three actions with a Bob's name on each, and the path to the writeup. Nothing was changed; say so. If anything is Critical, say that first, in bold, before anything else.
