# Agent Networking

The API container is attached only to `platform_net` and its full API is bound
to port 8000, published on loopback for local operators. Agents never share
that network. `agent-ingress` is the only bridge to `agents_net`; its Nginx
rules forward `/health` and `/internal/*` and return 403 for every other path.

The worker is attached to both networks so it can start external agents, call
their callbacks through `agent-ingress`, and use the Docker socket proxy. The
agent and `plain-coder` are attached only to `agents_net`, which is an internal
Docker network. Postgres, Redis, and the Docker socket proxy are only on
`platform_net`. LiteLLM is on both networks, has no published host port, and
agents receive only run-scoped virtual keys.

The Compose file starts Postgres with an init script that creates a separate
`litellm` database on a fresh Postgres volume. On an existing volume, create
that database once as the configured Postgres owner before starting LiteLLM.

With the required values in `.env`, run the isolated connectivity probe with:

```sh
docker compose --profile network-check run --rm --build plain-coder-network-check
```

The probe runs in the plain-coder image and must fail to connect to Postgres and
Redis, reach LiteLLM readiness and `/internal/health` through the ingress, reach
`/health`, and receive 403 for `/agents`.

The Compose services require `API_KEY`, `ENCRYPTION_KEY`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `REDIS_PASSWORD`, `LITELLM_MASTER_KEY`,
`OPENAI_API_KEY`, and `PLAIN_CODER_SECRET`. `LITELLM_MODEL` and
`LITELLM_UPSTREAM_MODEL` may select the client-facing alias and provider model.