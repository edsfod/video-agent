#!/bin/sh
# 把 scripts/githooks/ 里的钩子装进 .git/hooks/（全局 core.hooksPath 的钩子会转给这里）。重复运行无妨。
root=$(git rev-parse --show-toplevel)
hooks="$(git rev-parse --git-common-dir)/hooks"
mkdir -p "$hooks"
for name in pre-commit commit-msg pre-push; do
  printf '#!/bin/sh\nexec "%s/scripts/githooks/%s" "$@"\n' "$root" "$name" > "$hooks/$name"
  chmod +x "$hooks/$name" "$root/scripts/githooks/$name"
done
echo "已装：$hooks/pre-commit、$hooks/commit-msg、$hooks/pre-push"
