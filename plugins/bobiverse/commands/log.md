---
description: "Bob's log — append an entry to the Bobnet journal (.bobnet/journal.md). Cross-session memory the next Bob reads at startup. With no argument, summarizes this session."
argument-hint: "[what to record — default: summarize this session's work]"
allowed-tools: Read, Bash, Write, Edit
---

Bob's log. Entry: **$ARGUMENTS**

Append an entry to `.bobnet/journal.md` (create it with a `# Bobnet journal` heading if it doesn't exist). If no argument was given, summarize what this session actually did — check `git diff`/`git log` and the conversation, don't guess.

Format, exactly:

```markdown
## <YYYY-MM-DD HH:MM> — <one-line title>
- Did: <what changed — 1–3 bullets, with file/PR/commit refs>
- Decided: <decisions and the reason, or "none">
- Open: <loose threads the next session should know about, or "none">
- Bobs: <agents used, or "solo">
```

Rules:
- Under 10 lines. Facts, not narrative. Future-you is skimming this at session start.
- Decisions matter more than actions — "chose Airbyte over custom connector because X" is worth more than "edited 4 files."
- Never put secrets, credentials, or personal data in the journal. It's meant to be committed.
- If there's an in-progress Bender research file in `.bobnet/research/`, mention it under Open.

After writing, confirm in one line: the title you logged and the entry count in the journal.
