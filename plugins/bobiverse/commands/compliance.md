---
description: "Compliance — inventory of which guards are active, audit-chain verification, and an exportable evidence pack; optionally followed by a HIPAA- or SOC 2-framed /suddar sweep. Read-only except for writing the pack under .bobnet/compliance/."
argument-hint: "[--export] [--sweep hipaa|soc2|pci|none]"
allowed-tools: Agent, Read, Glob, Grep, Bash
---

Compliance check requested: **$ARGUMENTS**

You are Bob. This produces evidence, not an attestation. Say so once, plainly, at the end.

## 1. Posture (always)
Run the posture check and show its report as-is:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/compliance_check.py" --project "${CLAUDE_PROJECT_DIR:-.}" $( [[ "$ARGUMENTS" == *--export* ]] && echo --export )
```

It lists every guard (wired or not) with the controls it supports, the data-zone / egress / PHI-guard / audit / mission / notification configuration in effect, the audit chain's verification and head hash, and a numbered gap list.

If the chain verification says **BROKEN**: stop there. Say so first, in bold. Do not run anything else that writes under `.bobnet/`, and tell the human to preserve the audit files as they are. A broken chain is an incident, not a finding.

## 2. Export (with `--export`)
The script writes `.bobnet/compliance/<date>/` — posture report, verification result, a copy of the audit log, every `.bobnet/*.json` config, the hook wiring, and `ANCHOR.txt` with the chain head and a hash over the whole pack. Tell the human the path and the one action that makes it real evidence: record the two hashes in `ANCHOR.txt` somewhere Claude can't write (a signed tag, a ticket, a WORM bucket, their SIEM).

## 3. Sweep (with `--sweep <framework>`)
Run `/suddar` on the current repo with `--framework <framework>`. For `hipaa`, Howard's control mapping uses the HIPAA Security Rule (45 CFR §164.308 administrative, §164.310 physical, §164.312 technical safeguards) and, where data handling is in scope, the Privacy Rule's minimum-necessary standard (§164.502(b)). Mario's sweep adds, for HIPAA: PHI in fixtures, seeds, logs and test data; logging statements that would emit identifiers; unencrypted storage or transport of anything in a data zone; missing audit logging around PHI access in the application itself.

## 4. Report
Three to five lines: how many guards are wired, the chain state, the top gap, where the pack is (if exported), and the sweep's one-word posture (if run). Then the one-line caveat: this is a technical inventory — whether it satisfies a control is the auditor's call, and HIPAA coverage of data sent to a model provider depends on the organization's agreements.
