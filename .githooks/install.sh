#!/usr/bin/env bash
# .githooks/install.sh — activates this repo's tracked git hooks.
#
# Git never trusts a tracked hooks directory automatically, even though
# .githooks/ itself is committed and every clone gets the files — this is
# a deliberate git security decision (a hostile repo could otherwise ship
# a hook that runs arbitrary code the moment you commit). core.hooksPath
# has to be set explicitly, once, per clone. Run this once after cloning:
#
#   bash .githooks/install.sh
#
# See .githooks/README.md for what each hook actually does.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/commit-msg .githooks/pre-commit 2>/dev/null || true
echo "core.hooksPath set to .githooks — commit-msg and pre-commit are now active."
