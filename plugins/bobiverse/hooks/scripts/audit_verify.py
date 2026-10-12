#!/usr/bin/env python3
"""
audit_verify.py — check the Bobnet audit chain.

    python3 audit_verify.py [path/to/.bobnet/audit]     # default: ./.bobnet/audit

Exit 0 if the chain is intact, 1 if it's broken (prints the first bad line).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import verify  # noqa: E402

d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".bobnet/audit")
ok, n, msg = verify(d)
print(("OK  " if ok else "BROKEN  ") + msg)
sys.exit(0 if ok else 1)
