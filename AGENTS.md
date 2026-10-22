# Softmax CLI

Owns the `softmax` command, interactive Python login, browser callback and terminal output in the `softmax` namespace.
Read [package contracts](.contracts/index.md) and ancestor guidance. Change contracts only when explicitly requested.
Portable operations belong to [softmax-client](../../workspaces/softmax/client/python/AGENTS.md). Follow the root
E2E/system-only test policy.

Run from the repository root in the pinned Nix environment:

```sh
uv run --package softmax-cli ruff check packages/softmax-cli
uv run --package softmax-cli ty check packages/softmax-cli/src
bazel test //packages/softmax-cli/...
uv run lint-imports
```

Exercise real local authentication with isolated saved credentials before publishing changes to login or player
selection. Build the wheel and run its commands outside the checkout on Python 3.11 and 3.12. The
[publishing guide](../metta-dev/src/metta/setup/tools/PUBLISHING.md) owns release setup and order.
