# opencaselaw-mcp

A hosted MCP (Model Context Protocol) server for Swiss court decisions, designed to connect Claude Desktop and Claude.ai directly to the [opencaselaw.ch](https://opencaselaw.ch) dataset.

## What it does

Lets lawyers and legal researchers connect Claude to 1M+ Swiss court decisions via the Claude Desktop Connector UI. Users authenticate with an API key and can search decisions, retrieve full texts, and browse courts — all from within Claude.

## Features

- **OAuth 2.0** with PKCE — compatible with Claude.ai's native Connector UI
- **Streamable HTTP transport** — current MCP standard (SSE deprecated)
- **API key auth** — instant key generation, no account required
- **4 MCP tools**:
  - `search_decisions` — full-text search across decisions
  - `get_decision` — retrieve a specific decision by docket number
  - `list_courts` — list available Swiss courts
  - `get_statistics` — database statistics

## Data

Built on top of the [jonashertner/caselaw-repo-1](https://github.com/jonashertner/caselaw-repo-1) dataset (MIT). Daily sync from HuggingFace.

> **Note:** This repo currently runs with stub/mock data. Production requires the full index (~56 GB).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set your public base URL
export BASE_URL=https://mcp.opencaselaw.ch

uvicorn server:app --host 0.0.0.0 --port 8090
```

## Claude Desktop integration

1. Open Claude Desktop → Settings → Connectors → Add
2. Name: `Swiss Caselaw`, URL: `https://mcp.opencaselaw.ch/mcp`
3. Follow the OAuth flow — enter your API key when prompted
4. Done — search Swiss court decisions from Claude

## License

MIT — see [LICENSE](LICENSE)
