# Git Hooks — Enforcement, Not Convention

Two real `git` hooks live in this directory and are tracked in version
control (unlike `.git/hooks`, which is never committed). They exist because
both of the rules they enforce were previously **documented in memory and
violated anyway**, purely because following them depended on being
remembered at the exact moment of running `git commit`. A hook makes the
rule mechanical: git itself refuses the commit. No memory, no discipline,
no session continuity required.

**Activate once per clone** (git does not trust a tracked hooks dir
automatically — see `install.sh` for why):

```bash
bash .githooks/install.sh
```

---

## `commit-msg` — commit identity

**Rule:** this repo's git identity is Enoch (`enoch@wittycomp.com`), or
Lazarus (`lazarus@wittycomp.com`) for Buntyn-site work. Never "Claude", never
an `anthropic.com` or `claude.ai` address, never a `Claude-Session:` URL.

**Why a hook and not just a written rule:** documented in
`feedback_commit_identity.md` (lab memory) and violated four separate times
before this hook existed — each time because the session's own default
attribution template overrode the documented rule at the moment of
committing. A default template competing against a remembered rule loses
often enough that it isn't safe to rely on. A hook doesn't compete with
anything — it's the last thing that runs before the commit is accepted, and
it either accepts the message or it doesn't.

**What it checks:** the commit message (not the diff) for
`claude sonnet|claude opus|claude haiku|anthropic\.com|claude\.ai`
(case-insensitive). Any match rejects the commit with exit 1 and a message
telling you the correct attribution to use instead.

**No bypass.** If this fires, the fix is to rewrite the commit message, not
to work around the hook — there is no legitimate case where this repo wants
Claude/Anthropic attribution in a commit.

---

## `pre-commit` — secret scanner

**Rule:** no line being *added* in a commit may look like a live secret.

**Why this exists:** built 2026-09-11, immediately after finding a real,
live Vaultwarden master password committed in plaintext to
`wittycomp-lab`'s tracked history (`.claude/settings.local.json`), pushed to
both Forgejo and the GitHub mirror, present for months with nothing to catch
it. This hook cannot undo a secret already in history — that's a separate,
much bigger decision (rotate + scrub) — but it stops the *next* one from
ever landing, in any of the three lab repos that now carry it.

**What it checks:** only the lines this commit *adds*
(`git diff --cached -U0`) — never the whole tracked tree. Scanning the whole
tree would immediately and permanently block every future commit in a repo
that already has a historical exposure (exactly the situation that motivated
building this), which is a much bigger, separate decision than "should this
one new line be committed."

Patterns, in order:

| Check | Matches |
|---|---|
| GitHub token | `ghp_` + 36 chars, or `github_pat_...` |
| AWS access key | `AKIA` + 16 chars |
| Credential embedded in a URL | `scheme://<user>:<pass>@host` |
| PEM private key | `-----BEGIN ... PRIVATE KEY-----` |
| Secret-shaped env assignment | `*_PASSWORD=`, `*_SECRET=`, `*_TOKEN=`, `*_API_KEY=`, `*_CLIENTSECRET=` with a real-looking (non-empty, non-variable-reference) value |

A value is treated as a placeholder — not a real secret — and skipped when
it's empty, a shell/compose variable reference (`${VAR}` or `$VAR`), or
matches `changeme|xxxxx|your_..._|<...>|REDACTED|example.com|placeholder`
(case-insensitive).

**Bypass, when it's genuinely wrong:** add `# nosemgrep` to the end of the
specific line and re-commit — the same convention CLAUDE.md §4 already uses
for intentional credential lines edited via `sed` in `.env` files. Use it on
the one line that needs it, never as a blanket suppression for the whole
file or commit.

**Known limitation, accepted trade-off:** this is pattern-matching on text,
not real entropy analysis or a maintained signature database — consistent
with this lab's other hooks (see `warn-bash-over-mcp.sh`'s own documented
scope limits). It will miss a secret shaped like nothing on this list, and
it can false-positive on a line that merely *looks* like one (the fix for a
false positive is `# nosemgrep`, not disabling the hook).

**Testing changes to this hook**, before trusting it in any repo:

```bash
cd /tmp && mkdir t && cd t && git init -q
mkdir .githooks && cp <path-to-hook> .githooks/pre-commit && chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
git commit -q --allow-empty -m init
printf 'BW_PASSWORD=realsecrethere\n' > f && git add f  # nosemgrep
git commit -m test   # should be rejected
```

---

## Propagation

Both hooks are byte-identical across `wittycomp-lab`, `witty-intelligence`,
and `lazarus-build` as of 2026-09-11. `witty-intelligence` is the canonical
source going forward — a fix or new pattern goes there first, then gets
copied into the other two. There is no symlink-across-repos mechanism (git
hooks must be self-contained files within each repo, unlike the
`~/.claude/hooks` → `~/witty-intelligence/hooks` symlink, which works
because that's all one filesystem, not three independent git histories).
