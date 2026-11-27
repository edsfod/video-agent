#!/bin/sh
# 把 scripts/githooks/ 里的钩子装进 .git/hooks/（全局 core.hooksPath 的钩子会转给这里）。重复运行无妨。
# 装进去的钩子在运行时才找仓库的根目录：主目录和 git worktree 共用一份 .git/hooks，各自跑自己那份 scripts/githooks/。
hooks="$(git rev-parse --git-common-dir)/hooks"
mkdir -p "$hooks"
for name in pre-commit commit-msg pre-push; do
  printf '#!/bin/sh\nexec "$(git rev-parse --show-toplevel)/scripts/githooks/%s" "$@"\n' "$name" > "$hooks/$name"
  chmod +x "$hooks/$name" "$(git rev-parse --show-toplevel)/scripts/githooks/$name"
done
echo "已装：$hooks/pre-commit、$hooks/commit-msg、$hooks/pre-push"
