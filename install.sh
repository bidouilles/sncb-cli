#!/bin/sh
# Install the `sncb` CLI (via uv) and its Claude Code skill.
#   ./install.sh                 CLI + skill
#   ./install.sh --completion    also add zsh tab completion to ~/.zshrc
set -e
cd "$(dirname "$0")"
REPO="$(pwd)"

command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }

# 1. CLI → ~/.local/bin/sncb (editable: runs the code in this repo)
uv tool install --editable . --force

# 2. Skill → ~/.claude/skills/sncb (symlink to skill/, so updates follow the repo)
SKILLS="$HOME/.claude/skills"
mkdir -p "$SKILLS"
if [ -e "$SKILLS/sncb" ] && [ ! -L "$SKILLS/sncb" ]; then
  echo "$SKILLS/sncb exists and is not a symlink; move it away and re-run." >&2
  exit 1
fi
ln -sfn "$REPO/skill" "$SKILLS/sncb"
echo "Skill linked: $SKILLS/sncb -> $REPO/skill"

# 3. Optional zsh completion
if [ "$1" = "--completion" ]; then
  LINE='eval "$(sncb completion zsh)"'
  if grep -qxF "$LINE" "$HOME/.zshrc" 2>/dev/null; then
    echo "zsh completion already in ~/.zshrc"
  else
    printf '\n# sncb tab completion\n%s\n' "$LINE" >> "$HOME/.zshrc"
    echo "zsh completion added to ~/.zshrc (open a new shell)"
  fi
fi

echo "Done. Try: sncb Charleroi-Central Ottignies"
