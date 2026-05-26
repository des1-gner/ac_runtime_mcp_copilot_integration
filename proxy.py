"""
Local SigV4-signing proxy for AgentCore Runtime MCP servers.

Sits between your MCP client (e.g. VS Code Copilot) and the AgentCore Runtime endpoint.
Receives plain HTTP MCP requests on localhost, signs them with SigV4, and forwards
them to the Runtime.

Usage:
    python proxy.py

Then point your MCP client at: http://localhost:8080/mcp

Requires AWS credentials in your environment.
"""

import json
from urllib.parse import quote

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response
from starlette.routing import Route
import uvicorn

# ============================================================
# Configuration — update these for your deployment
# ============================================================
REGION = "<YOUR_AWS_REGION>"
AGENT_ARN = "arn:aws:bedrock-agentcore:<YOUR_AWS_REGION>:<YOUR_AWS_ACCOUNT_ID>:runtime/<YOUR_RUNTIME_ID>"
LOCAL_PORT = 8080

# Construct the Runtime MCP endpoint URL
ENCODED_ARN = quote(AGENT_ARN, safe="")
RUNTIME_URL = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT"

# AWS credentials
boto_session = boto3.Session(region_name=REGION)


def get_signed_headers(method: str, url: str, headers: dict, body: bytes) -> dict:
    """Sign a request with SigV4 and return the full set of headers."""
    credentials = boto_session.get_credentials().get_frozen_credentials()
    aws_request = AWSRequest(method=method, url=url, headers=headers, data=body)
    SigV4Auth(credentials, "bedrock-agentcore", REGION).add_auth(aws_request)
    return dict(aws_request.headers)


async def proxy_mcp(request: Request) -> Response:
    """Proxy an MCP request to AgentCore Runtime with SigV4 signing."""
    body = await request.body()

    print(f"  → Proxying: {body[:200].decode()}")

    # Build headers to forward
    forward_headers = {
        "Content-Type": request.headers.get("content-type", "application/json"),
        "Accept": request.headers.get("accept", "application/json, text/event-stream"),
    }

    # Forward MCP session ID if present
    if "mcp-session-id" in request.headers:
        forward_headers["Mcp-Session-Id"] = request.headers["mcp-session-id"]

    # Forward AgentCore session ID if present
    if "x-amzn-bedrock-agentcore-runtime-session-id" in request.headers:
        forward_headers["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"] = request.headers[
            "x-amzn-bedrock-agentcore-runtime-session-id"
        ]

    # Sign the request
    signed_headers = get_signed_headers("POST", RUNTIME_URL, forward_headers, body)

    # Stream the response back to the client
    client = httpx.AsyncClient(timeout=120.0)
    try:
        req = client.build_request("POST", RUNTIME_URL, headers=signed_headers, content=body)
        response = await client.send(req, stream=True)

        # Build response headers
        response_headers = {}
        if "mcp-session-id" in response.headers:
            response_headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
        if "content-type" in response.headers:
            response_headers["Content-Type"] = response.headers["content-type"]

        print(f"  ← Status: {response.status_code}, Content-Type: {response.headers.get('content-type', 'unknown')}")

        async def stream_body():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_body(),
            status_code=response.status_code,
            headers=response_headers,
        )
    except Exception as e:
        await client.aclose()
        print(f"  ✗ Error: {e}")
        return Response(content=str(e), status_code=502)


# Starlette app
app = Starlette(
    routes=[
        Route("/mcp", proxy_mcp, methods=["POST", "GET", "DELETE"]),
    ]
)


if __name__ == "__main__":
    print(f"🚀 SigV4 Proxy starting on http://localhost:{LOCAL_PORT}/mcp")
    print(f"   Forwarding to: {RUNTIME_URL[:80]}...")
    print(f"   Region: {REGION}")
    print(f"   Agent ARN: {AGENT_ARN}")
    print()
    print("Point your MCP client at: http://localhost:8080/mcp")
    print()
    uvicorn.run(app, host="0.0.0.0", port=LOCAL_PORT)
