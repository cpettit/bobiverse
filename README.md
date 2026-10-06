# Bobiverse — Claude Code plugin marketplace

This repo is a [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces). It currently hosts one plugin, **bobiverse**: a crew of twenty agents, twelve commands, and nine enforcement hooks modeled on Dennis E. Taylor's *Bobiverse*. The plugin's own README is at [`plugins/bobiverse/README.md`](plugins/bobiverse/README.md).

## Install

```
/plugin marketplace add cpettit/bobiverse
/plugin install bobiverse@bobiverse
```

Or from the shell:

```bash
claude plugin marketplace add cpettit/bobiverse
claude plugin install bobiverse@bobiverse            # user scope
claude plugin install bobiverse@bobiverse --scope project
```

Then `/agents` lists the Bobs and `/moot <question>` convenes them.

### Pin to a release

```
/plugin marketplace add cpettit/bobiverse#v0.2.0
```

### Update

```
/plugin marketplace update bobiverse
/plugin update bobiverse@bobiverse
```

Updates compare the git commit, not the `version` field — so any push to the branch you added from is an update. Pin a tag if you want stability.

## Team / project auto-install

Commit this to a project's `.claude/settings.json` and everyone who opens the repo in Claude Code gets prompted to install:

```json
{
  "extraKnownMarketplaces": {
    "bobiverse": {
      "source": { "source": "github", "repo": "cpettit/bobiverse" }
    }
  },
  "enabledPlugins": ["bobiverse@bobiverse"]
}
```

## Private repo

Works unchanged. Claude Code uses your existing git credentials — `gh auth`, SSH keys, or a credential helper. For GitHub shorthand it tries SSH first and falls back to HTTPS; set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` to skip the SSH probe.

## Layout

```
.claude-plugin/marketplace.json   ← the marketplace manifest (this is what makes the repo a marketplace)
plugins/
└── bobiverse/                    ← the plugin
    ├── .claude-plugin/plugin.json
    ├── agents/  commands/  hooks/  output-styles/  statusline/  scripts/
    └── README.md
.github/workflows/validate.yml    ← CI: validates both manifests and smoke-tests the hooks
```

## Adding another plugin

1. Create `plugins/<name>/` with a `.claude-plugin/plugin.json` (only `name` is required).
2. Add an entry to `.claude-plugin/marketplace.json`:
   ```json
   { "name": "<name>", "source": "./plugins/<name>", "description": "..." }
   ```
3. `claude plugin validate .` — CI does the same on push.

A plugin can also live in its own repo; point at it with `"source": { "source": "github", "repo": "owner/repo", "ref": "v1.0.0" }`.

## Releasing

```bash
# bump plugins/bobiverse/.claude-plugin/plugin.json "version", then:
git tag v0.3.0 && git push --tags
```

Users on `#v0.2.0` stay there; users on the default branch pick it up at their next `/plugin update`.

---
*Bobiverse characters are the creation of Dennis E. Taylor. This is a fan project; nothing here is affiliated with or endorsed by the author or publisher.*
