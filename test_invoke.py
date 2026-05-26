"""
Direct test of the AgentCore Runtime MCP endpoint with SigV4 signing.
No proxy, no async — just a simple signed request to see what comes back.

Usage:
    python test_invoke.py

Requires AWS credentials in your environment.
"""

import json
from urllib.parse import quote

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests

# Configuration — update these for your deployment
REGION = "<YOUR_AWS_REGION>"
AGENT_ARN = "arn:aws:bedrock-agentcore:<YOUR_AWS_REGION>:<YOUR_AWS_ACCOUNT_ID>:runtime/<YOUR_RUNTIME_ID>"

ENCODED_ARN = quote(AGENT_ARN, safe="")
URL = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT"

# MCP initialize payload
body = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0.0"},
    },
})

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

# Sign with SigV4
session = boto3.Session(region_name=REGION)
credentials = session.get_credentials().get_frozen_credentials()
aws_request = AWSRequest(method="POST", url=URL, headers=headers, data=body)
SigV4Auth(credentials, "bedrock-agentcore", REGION).add_auth(aws_request)
signed_headers = dict(aws_request.headers)

print(f"URL: {URL[:100]}...")
print(f"Body: {body}")
print(f"Sending request...")
print()

# Make the request with a long timeout
response = requests.post(URL, headers=signed_headers, data=body, timeout=120, stream=True)

print(f"Status: {response.status_code}")
print(f"Response Headers:")
for k, v in response.headers.items():
    print(f"  {k}: {v}")
print()
print("Response Body:")
for chunk in response.iter_content(chunk_size=None):
    if chunk:
        print(chunk.decode())
