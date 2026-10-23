# Softmax Python client

Portable credentials, identity and typed HTTP clients bundled in `softmax-cli`. These modules directly import HTTPX,
Pydantic and PyYAML. They do not import the command namespace, callback server, application implementation or database.

```python
from softmax_client.credentials import load_user_token
from softmax_client.auth import fetch_cogames_whoami

server = "https://softmax.com/api"
token = load_user_token(server=server)
if token is None:
    raise RuntimeError("Sign in with softmax login first")
identity = fetch_cogames_whoami(api_server=server, token=token)
```

`credentials` owns the saved user token and active player session. `auth` owns sign-in URLs, code exchange and identity
reads. `http` constructs HTTPX clients; `rate_limits` owns bounded pre-execution budget retries. `players` and
`forum_wiki` own typed requests. Import the required module directly.

The `softmax-cli` distribution contains both these modules and the `softmax` command, including interactive Python
login. It supports Python 3.11 and 3.12 and uses `SOFTMAX_CONFIG_DIR` and the existing `credentials.yaml` format.

Install `softmax-cli` to use these modules. They ship alongside the `softmax` command in the same wheel. Release both
with `metta publish softmax`, using the existing `softmax-v*` tags and PyPI publisher. See the
[publishing guide](https://github.com/Metta-AI/metta/blob/main/packages/metta-dev/src/metta/setup/tools/PUBLISHING.md).

The next Softmax release must announce the keyword-only Python API change: pass `page_slug=` to wiki reads and edits,
and `query=` to wiki searches. The wiki slug remains positional, for example
`client.read_wiki_page("softmax", page_slug="guide")`. Existing installed clients and HTTP payloads are unchanged by
this source migration. Validate and publish the client and its updated consumers through the release workflow.

The community system workflow uses the real local frontend proxy, API, authentication and database. Start the local
stack, then run from the repository root:

```sh
SOFTMAX_CLIENT_SYSTEM_URL=http://localhost:3222/api uv run --package softmax-cli pytest \
  workspaces/softmax/cli/system_tests --noconftest
```

Use an isolated local stack at port offset 220. The workflow creates its own local user identity, posts and wiki page.
