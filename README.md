<p align="center">
  <img src="https://raw.githubusercontent.com/aranjan/icici-mcp/main/logo.svg" alt="icici-mcp logo" width="128" height="128">
</p>

<h1 align="center">icici-mcp</h1>

<p align="center">
  <a href="https://pypi.org/project/icici-mcp/"><img src="https://badge.fury.io/py/icici-mcp.svg" alt="PyPI version"></a>
  <a href="https://github.com/aranjan/icici-mcp/actions/workflows/ci.yml"><img src="https://github.com/aranjan/icici-mcp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://smithery.ai/servers/aranjan/icici-mcp"><img src="https://smithery.ai/badge/aranjan/icici-mcp" alt="Smithery"></a>
</p>

MCP server for [ICICI Direct](https://www.icicidirect.com/) -- monitor Indian stocks and portfolios through any [MCP-compatible](https://modelcontextprotocol.io/) AI assistant.

## Why an MCP server instead of a Python library?

Traditional Breeze Connect wrappers require you to write Python code to trade. With icici-mcp, you just talk:

```
You:       "How's my portfolio doing?"
Assistant: fetches holdings, calculates P&L, summarizes gainers and losers

You:       "Show me a NIFTY futures quote"
Assistant: fetches a quote for the specified contract
```

No code. No scripts. No terminal. Just conversation.

icici-mcp connects an assistant to your ICICI Direct account with portfolio and market-data tools and manual daily login.

## How it works

```
You (natural language) --> AI Assistant --> icici-mcp (MCP server) --> ICICI Direct Breeze API
```

Your AI assistant can retrieve portfolio and market data through the MCP protocol. After manual login, the server reuses the cached token while it remains valid.

## Features

10 tools for authentication, portfolio monitoring, and market data:

| Tool | Description |
|------|-------------|
| `icici_login` | Authenticate using a cached or manually supplied session token |
| `get_holdings` | Portfolio holdings with P&L |
| `get_demat_holdings` | All shares in your demat account |
| `get_positions` | Today's open positions |
| `get_orders` | Order history for a date range |
| `get_margins` | Available margins for trading |
| `get_funds` | Available funds in your account |
| `get_quote` | Live market quotes (equity and F&O) |
| `get_historical_data` | Historical OHLCV candle data |
| `get_option_chain` | Option chain quotes (see known limitation below) |

Live trading tools are not exposed through MCP. They must not be re-enabled
until server-side authorization, order-specific explicit approval, risk
validation, audit logging, and a kill switch are implemented. The login tool
can still authenticate and update the local session-token cache. The existing
Python order functions remain callable directly; this restriction applies to
MCP exposure.

**Key capabilities:**
- Manual ICICI login with a shared daily session cache
- Supports equity and F&O market data
- Quotes are point-in-time snapshots, not a streaming feed

The option-chain request tested for NIFTY was rejected by Breeze because it
required a right or strike price; this tool does not currently expose either
parameter. Individual option quotes and historical candles have worked.

## Compatible with

Works with any MCP-compatible client, including:

| Client | Platform |
|--------|----------|
| [Claude Desktop](https://claude.ai/download) | macOS, Windows |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | Terminal (macOS, Linux, Windows) |
| [Cursor](https://cursor.sh/) | macOS, Windows, Linux |
| [Windsurf](https://codeium.com/windsurf) | macOS, Windows, Linux |
| [Continue](https://continue.dev/) | VS Code, JetBrains |
| Any MCP-compatible client | See [MCP clients list](https://modelcontextprotocol.io/clients) |

## Docker and Open WebUI setup

The Compose service runs mcpo and the stdio MCP server in one container.
Docker, Docker Compose, and an existing external `docker-net-private` network
are required. Open WebUI must also be connected to that network. If using a
different network, update its name in `compose.yaml`.

From the deployed checkout on the Linux host:

```bash
cd /opt/trikon/icici-mcp  # or your checkout directory
docker network inspect docker-net-private
cp .env.example .env
chmod 600 .env
# Privately edit .env: set ICICI_API_KEY, ICICI_API_SECRET and MCPO_API_KEY.
docker compose up -d --build
docker compose ps
```

Use a separate strong random value for `MCPO_API_KEY`; do not reuse an ICICI
credential. Follow Docker Compose `.env` quoting rules for special characters.
Do not set `ICICI_SESSION_TOKEN` in `.env` when using the interactive daily
login. Keep `.env` private: it is excluded from Git and the Docker build.
If the checkout is root-owned, use an authorized root shell (for example
`sudo -i`) before running these commands.

mcpo runs in single-server mode; **there is no separate mcpo JSON config
file**. The Dockerfile starts it with strict authentication, port 8000, and
`icici-mcp` as its stdio backend. The host port is bound to
`127.0.0.1:8000`; the network alias is `icici-mcp`.

In Open WebUI, add an OpenAPI tool server at `http://icici-mcp:8000`, using
`MCPO_API_KEY` for bearer authentication. The schema is at
`http://icici-mcp:8000/openapi.json`; there is no `/icici` path prefix.
The external Docker network is shared and the connection uses unencrypted
HTTP. Limit which containers join it and do not expose the port publicly;
remote access requires a separately secured, TLS-enabled deployment.

### Daily manual ICICI login

The Breeze session is needed for read-only quotes and historical data as well
as account operations. Before using the service on a new India calendar day,
or whenever ICICI rejects the cached session:

```bash
cd /opt/trikon/icici-mcp  # or your checkout directory
docker compose up -d
docker compose exec icici icici-mcp-login
```

1. Open the official ICICI login URL displayed by the command in your own
   browser and complete ICICI's login.
2. Copy only the `apisession` value from the redirect URL and paste it into
   the hidden terminal prompt. Do not share the token, redirect URL, API keys,
   or credentials in chat.
3. Wait for `Login successful. Session token cached for today.` The CLI
   validates the token with Breeze before replacing the cache.

The server reads the shared `icici-session` volume on subsequent requests;
no restart or token copying into `.env` is needed. The cache is valid only for
the current India calendar day, and ICICI may invalidate it earlier. ICICI
describes session-key expiry as 24 hours or midnight
([guidance](https://www.icicidirect.com/ilearn/stocks/articles/how-to-generate-session-key-and-install-sdk-for-breeze-api)).
The volume contains a sensitive token; protect access to the Docker host and
backups. No TOTP automation is used.

For a read-only check, request a quote using an ICICI stock code, such as
`ICIBAN`. A successful HTTP response alone is not enough: check the Breeze
`Status` and `Error` in the response. If authentication fails, repeat the
manual login; if Open WebUI cannot connect, check the container, shared
network, URL, and bearer key. Avoid sharing logs containing credentials.

## Local stdio setup

Install this checkout with `pip install .` and configure your MCP client:

Add this to your MCP client configuration. The config location depends on your client -- refer to your client's documentation for the exact path.

```json
{
  "mcpServers": {
    "icici": {
      "command": "icici-mcp",
      "env": {
        "ICICI_API_KEY": "your-api-key",
        "ICICI_API_SECRET": "your-api-secret"
      }
    }
  }
}
```

Run `icici-mcp-login` with the same API key and secret in its environment, then
restart your MCP client. The CLI and server must run as the same user to share
the cache.

### Try it out

Open a new chat and try:

- "Show my portfolio holdings"
- "What's the ICIBAN quote?"
- "How much cash do I have available?"
- "Show me a quote for the specified NIFTY futures contract"

Breeze uses ICICI stock codes, which can differ from NSE symbols. Provide the
contract expiry and, for options, the strike and call/put where required.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ICICI_API_KEY` | Yes | ICICI Direct API key |
| `ICICI_API_SECRET` | Yes | ICICI Direct API secret |
| `MCPO_API_KEY` | Container only | Separate key required to access the local mcpo HTTP API |
| `ICICI_SESSION_TOKEN` | No | Manually obtained API session token; avoid setting this for the container's daily interactive login |

## Manual Login

Use `icici-mcp-login` as described above. The CLI accepts the API session token
returned by ICICI's official login; it never asks for your password or TOTP.

## Use Cases

- **Daily portfolio monitoring** -- "Give me a summary of my portfolio with top gainers and losers"
- **F&O research** -- "Show me a quote for a specified NIFTY option"
- **Research** -- "What's the 52-week high of HDFC Bank?"
- **Scheduled reports** -- Combine with MCP scheduled tasks to get a daily portfolio summary at 9am

## Roadmap

- [ ] Basket orders -- place multiple orders in one command
- [ ] Mutual fund tools -- buy, redeem, check SIPs
- [ ] IPO application tools
- [ ] Portfolio analytics -- sector allocation, diversification score
- [ ] Multi-account support

Have an idea? [Open a feature request](https://github.com/aranjan/icici-mcp/issues/new?template=feature_request.md).

## Development

```bash
git clone https://github.com/aranjan/icici-mcp.git
cd icici-mcp
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Security

- Credentials are passed via environment variables -- never stored in code
- Session tokens are cached locally at `~/.icici_direct_token.json` and expire daily
- The server runs locally on your machine -- no data is sent to third-party servers
- All communication with ICICI Direct uses HTTPS

## License

MIT
