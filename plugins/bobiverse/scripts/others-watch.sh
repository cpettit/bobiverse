#!/usr/bin/env bash
# others-watch.sh — run the Others watch unattended against one or more repos.
#
# Usage:
#   scripts/others-watch.sh /path/to/repo [/path/to/another ...]
#
# Schedule it (examples):
#   # cron, nightly at 03:17
#   17 3 * * *  /path/to/bobiverse/scripts/others-watch.sh ~/src/app ~/src/infra >> ~/.bobnet-watch.log 2>&1
#
#   # systemd user timer: see others-watch.service / .timer below (generated with --install-systemd)
#
# Environment:
#   SCUT_NTFY_URL / SCUT_WEBHOOK_URL   where to ping on High/Critical (optional)
#   BOBIVERSE_PLUGIN_DIR               path to this plugin (default: dir above this script)
#   CLAUDE_BIN                         claude binary (default: claude)
#
# Each repo gets its own non-interactive Claude run with the plugin loaded and
# permissions constrained to read-only tools plus writing under .bobnet/.
set -euo pipefail

PLUGIN_DIR="${BOBIVERSE_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CLAUDE="${CLAUDE_BIN:-claude}"

if [[ "${1:-}" == "--install-systemd" ]]; then
  shift
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/others-watch.service <<EOF
[Unit]
Description=Bobiverse Others watch — dependency/CVE/secret sweep

[Service]
Type=oneshot
Environment=BOBIVERSE_PLUGIN_DIR=${PLUGIN_DIR}
${SCUT_NTFY_URL:+Environment=SCUT_NTFY_URL=${SCUT_NTFY_URL}}
${SCUT_WEBHOOK_URL:+Environment=SCUT_WEBHOOK_URL=${SCUT_WEBHOOK_URL}}
ExecStart=${PLUGIN_DIR}/scripts/others-watch.sh $*
EOF
  cat > ~/.config/systemd/user/others-watch.timer <<'EOF'
[Unit]
Description=Nightly Others watch

[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now others-watch.timer
  echo "Installed and started others-watch.timer for: $*"
  systemctl --user list-timers others-watch.timer --no-pager
  exit 0
fi

if [[ $# -eq 0 ]]; then
  echo "usage: $0 /path/to/repo [...]   |   $0 --install-systemd /path/to/repo [...]" >&2
  exit 1
fi

status=0
for repo in "$@"; do
  if [[ ! -d "$repo" ]]; then
    echo "[others-watch] skip: $repo is not a directory" >&2
    continue
  fi
  echo "[others-watch] $(date -Is) scanning $repo"
  (
    cd "$repo"
    # -p: non-interactive. Tools limited to read + the scanners + writing the report.
    "$CLAUDE" -p "/others-watch --fail-on high" \
      --plugin-dir "$PLUGIN_DIR" \
      --allowedTools "Read,Glob,Grep,Agent,Bash(npm audit*),Bash(pip-audit*),Bash(osv-scanner*),Bash(trivy*),Bash(grype*),Bash(cargo audit*),Bash(govulncheck*),Bash(bundle audit*),Bash(checkov*),Bash(tfsec*),Bash(hadolint*),Bash(gitleaks*),Bash(trufflehog*),Bash(git log*),Bash(git diff*),Bash(git status*),Bash(ls*),Bash(cat*),Bash(find*),Bash(stat*),Bash(python3 *scut.py*),Write(.bobnet/**),Edit(.bobnet/**)" \
      --max-turns 40 \
      --output-format text
  ) | tee /tmp/others-watch-last.txt || status=1
  if grep -q '^OTHERS-WATCH: ALERT' /tmp/others-watch-last.txt; then
    echo "[others-watch] ALERT in $repo"
    status=2
  fi
done
exit $status
