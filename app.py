"""
Dummy AWS Cost and Billing MCP Server for AgentCore Runtime.

This is a minimal MCP server that exposes a few simple tools
to verify connectivity from an MCP client (e.g. VS Code with Copilot/Kiro).

AgentCore Runtime expects the MCP server at 0.0.0.0:8000/mcp
"""

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server — must bind to 0.0.0.0:8000 for AgentCore Runtime
mcp = FastMCP(host="0.0.0.0", stateless_http=True)


@mcp.tool()
def get_monthly_summary() -> dict:
    """Get a summary of AWS costs for the current month."""
    return {
        "month": "May 2026",
        "total_cost": "$142.37",
        "currency": "USD",
        "services": [
            {"name": "Amazon EC2", "cost": "$62.10"},
            {"name": "Amazon S3", "cost": "$23.45"},
            {"name": "Amazon Bedrock", "cost": "$41.82"},
            {"name": "AWS Lambda", "cost": "$15.00"},
        ],
        "status": "This is a dummy response to verify MCP connectivity.",
    }


@mcp.tool()
def get_service_cost(service_name: str) -> dict:
    """Get the cost breakdown for a specific AWS service.

    Args:
        service_name: The name of the AWS service (e.g. 'EC2', 'S3', 'Bedrock')
    """
    dummy_costs = {
        "ec2": {"service": "Amazon EC2", "cost": "$62.10", "instances": 3},
        "s3": {"service": "Amazon S3", "cost": "$23.45", "buckets": 12},
        "bedrock": {"service": "Amazon Bedrock", "cost": "$41.82", "invocations": 1547},
        "lambda": {"service": "AWS Lambda", "cost": "$15.00", "functions": 8},
    }

    key = service_name.lower().strip()
    if key in dummy_costs:
        return dummy_costs[key]

    return {
        "service": service_name,
        "cost": "N/A",
        "message": f"No dummy data for '{service_name}'. Try: EC2, S3, Bedrock, or Lambda.",
    }


@mcp.tool()
def ping() -> dict:
    """Simple connectivity test. Returns a confirmation that the MCP server is reachable."""
    return {
        "status": "ok",
        "message": "MCP server is reachable on AgentCore Runtime!",
        "server": "aws-billing-mcp",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
