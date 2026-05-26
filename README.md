# Deploying an MCP Server on Amazon Bedrock AgentCore Runtime

A complete guide to deploying a Model Context Protocol (MCP) server on Amazon Bedrock AgentCore Runtime and connecting to it from VS Code (GitHub Copilot, Kiro, or other MCP clients).

## Overview

This project demonstrates how to:
1. Build a simple MCP server with tools
2. Test it locally
3. Deploy it to AgentCore Runtime
4. Connect to it from an MCP client in VS Code via a local SigV4-signing proxy

## Architecture

```
┌─────────────────┐       ┌──────────────┐       ┌─────────────────────────────┐
│  MCP Client     │──────▶│  SigV4 Proxy │──────▶│  AgentCore Runtime          │
│  (VS Code)      │ HTTP  │  (localhost)  │ HTTPS │  (MCP Server on 0.0.0.0:8000) │
│                 │◀──────│              │◀──────│                             │
└─────────────────┘       └──────────────┘       └─────────────────────────────┘
```

MCP clients like GitHub Copilot send plain HTTP requests. AgentCore Runtime requires SigV4 authentication on every request. The proxy bridges this gap by signing requests locally before forwarding them.

## Prerequisites

- Python 3.10+
- AWS CLI installed and configured with credentials
- `pip install bedrock-agentcore mcp boto3 httpx starlette uvicorn requests`
- An AWS account with Amazon Bedrock AgentCore permissions

## Project Structure

```
billingMCP/
├── app.py                      # MCP server code (deployed to Runtime)
├── test_local.py               # Local test version (no deployment needed)
├── test_invoke.py              # Direct SigV4-signed test against Runtime
├── proxy.py                    # Local SigV4 proxy for MCP clients
├── mcp.json                    # VS Code Copilot MCP client config
├── requirements.txt            # Python dependencies for deployment
├── .bedrock_agentcore.yaml     # AgentCore CLI deployment config
└── README.md
```

## Step 1: Create Your MCP Server

`app.py` is the MCP server that gets deployed to Runtime. It must meet the [MCP protocol contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html):

| Requirement | Value |
|-------------|-------|
| Host | `0.0.0.0` |
| Port | `8000` |
| Path | `/mcp` |
| Transport | `streamable-http` |
| Mode | `stateless_http=True` |

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

@mcp.tool()
def ping() -> dict:
    """Simple connectivity test."""
    return {"status": "ok", "message": "MCP server is reachable!"}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

The only dependency needed in `requirements.txt` is:

```
mcp
```

## Step 2: Test Locally

Before deploying, verify the server works locally:

```bash
python test_local.py
```

This starts the MCP server on `http://localhost:8080/mcp`. Test with curl:

```bash
# Step 1: Initialize (note the Mcp-Session-Id in response headers)
curl -i -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0.0"}}}'

# Step 2: List tools (use the Mcp-Session-Id from above)
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <session-id-from-step-1>" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'

# Step 3: Call a tool
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <session-id-from-step-1>" \
  -d '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ping", "arguments": {}}}'
```

> **Note:** The MCP streamable-http transport requires the `Accept: application/json, text/event-stream` header. Without it you'll get a "Not Acceptable" error.

## Step 3: Deploy to AgentCore Runtime

### Configure deployment

Edit `.bedrock_agentcore.yaml` and fill in your values:

```yaml
default_agent: awsBillingMcp
agents:
  awsBillingMcp:
    name: awsBillingMcp
    language: python
    entrypoint: app.py
    deployment_type: direct_code_deploy
    runtime_type: PYTHON_3_13
    aws:
      execution_role_auto_create: true
      account: '<YOUR_AWS_ACCOUNT_ID>'
      region: <YOUR_AWS_REGION>
      network_configuration:
        network_mode: PUBLIC
      protocol_configuration:
        server_protocol: MCP    # <-- CRITICAL: must be MCP, not HTTP
      observability:
        enabled: true
```

> **Important:** `server_protocol: MCP` tells the Runtime to route requests to `/mcp` on port 8000 using MCP protocol passthrough. If you set this to `HTTP`, the Runtime will treat it as a generic HTTP agent and MCP requests will hang/fail.

### Deploy

```bash
agentcore deploy -a awsBillingMcp
```

On success you'll get an Agent ARN like:
```
arn:aws:bedrock-agentcore:<region>:<account-id>:runtime/awsBillingMcp-<random-id>
```

### Verify deployment

```bash
agentcore status
```

Check CloudWatch logs to confirm the server started:
```
INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Test directly with SigV4

`test_invoke.py` sends a SigV4-signed MCP initialize request directly to the Runtime endpoint:

```bash
python test_invoke.py
```

Expected output:
```
Status: 200
Response Body:
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-03-26",...}}
```

## Step 4: Connect from VS Code

AgentCore Runtime requires SigV4 authentication, but MCP clients (GitHub Copilot, Kiro, etc.) send plain HTTP. You need a local proxy to bridge this.

### Start the SigV4 proxy

Edit `proxy.py` and set your `REGION` and `AGENT_ARN`, then:

```bash
python proxy.py
```

Output:
```
🚀 SigV4 Proxy starting on http://localhost:8080/mcp
   Forwarding to: https://bedrock-agentcore.<region>.amazonaws.com/runtimes/...
```

### Add the MCP server in VS Code

Open the Command Palette (Cmd+Shift+P) → **MCP: Add Server** → select **HTTP** → enter the URL:

```
http://localhost:8080/mcp
```

![Adding the MCP server URL in VS Code](Screenshot%202026-05-26%20at%2013.05.39.png)

Alternatively, create/edit `mcp.json` in your project root:

```json
{
  "servers": {
    "aws-billing-mcp": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

> **Note for GitHub Copilot:** Copilot uses `"servers"` as the top-level key. Other clients (Kiro, Cursor, Claude Code) use `"mcpServers"`.

### Confirm the connection

![MCP server connected in VS Code](Screenshot%202026-05-26%20at%2013.05.26.png)

### Use it

Open Copilot Chat and ask something that triggers the tools:

```
What's my AWS billing summary for this month?
```

![Example of Copilot using the MCP server tools](Screenshot%202026-05-26%20at%2013.06.45.png)

## Troubleshooting

### "Not Acceptable" error on curl

You're missing the `Accept` header. MCP streamable-http requires:
```
Accept: application/json, text/event-stream
```

### Deployment fails with name validation error

Agent runtime names cannot contain hyphens. Use camelCase (e.g. `awsBillingMcp` not `aws-billing-mcp`).

### Server binds to 127.0.0.1 instead of 0.0.0.0

Your `FastMCP()` constructor must specify `host="0.0.0.0"`. Without this, the Runtime infrastructure cannot reach your server.

### `server_protocol: HTTP` causes requests to hang

If you deployed with `server_protocol: HTTP`, the Runtime treats your server as a generic HTTP agent and won't forward MCP protocol messages correctly. Change to `server_protocol: MCP` and redeploy.

### Proxy hangs or times out

This usually means the Runtime is cold-starting. First invocation can take 10-30 seconds. If it persists, check CloudWatch logs to see if the request reached your server.

### CloudWatch shows "WARNING: Invalid HTTP request received"

This is typically from the Runtime's health check probe hitting your server before it's fully ready. It's harmless — your MCP server will still work for actual MCP requests.

## Known Issue: GitHub Copilot Organisation MCP Access Policy

If your organisation manages GitHub Copilot settings, you may see:

> "This MCP Server is disabled because it is configured to be disabled in the Editor."

![MCP server disabled by org policy](Screenshot%202026-05-26%20at%2013.06.03.png)

This happens when the org-level **Chat › Mcp: Access** policy is set to `registry`, meaning only pre-approved MCP servers from the GitHub Copilot registry are allowed. Custom servers (including `http://localhost:8080/mcp`) are force-disabled.

**To resolve:**
- Ask your GitHub Copilot organisation admin to change the MCP access policy to allow custom servers, or register your server as an approved target
- See: [GitHub docs — Configure MCP server access](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-mcp-usage/configure-mcp-server-access)

**Workarounds:**
- Use a different MCP client that isn't subject to the org policy (Kiro, Cursor, Claude Code, Amazon Q)
- Some MCP clients allow you to configure custom auth headers and SigV4 signing directly, removing the need for a proxy entirely

## References

- [Deploy MCP servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [MCP protocol contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp-protocol-contract.html)
- [GitHub Copilot MCP server configuration](https://code.visualstudio.com/docs/copilot/chat/mcp-servers)
- [Configure MCP server access (org-level)](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-mcp-usage/configure-mcp-server-access)
