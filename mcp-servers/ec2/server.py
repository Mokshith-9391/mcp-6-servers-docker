"""
EC2 MCP Server
==============
Gives the agent tools to look at (and optionally start/stop) EC2 instances:
  - list_instances(state, region)
  - describe_instance(instance_id, region)
  - get_instance_summary(region)
  - start_instance(instance_id, region)   <- only if EC2_ALLOW_WRITE=true
  - stop_instance(instance_id, region)    <- only if EC2_ALLOW_WRITE=true

AWS credentials:
  On EC2 -> attach an IAM Role to the instance (see deploy/iam/). boto3 picks it
  up automatically. Never hard-code access keys.

Run it:
    python server.py
It listens at: http://127.0.0.1:8003/mcp
"""

import os
from collections import Counter

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()  # local runs: finds the project .env | Docker: env comes from compose

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("EC2_PORT", "8003"))
DEFAULT_REGION = os.getenv("AWS_REGION", "ap-south-1")
ALLOW_WRITE = os.getenv("EC2_ALLOW_WRITE", "false").strip().lower() == "true"

mcp = FastMCP("ec2", host=HOST, port=PORT)

VALID_STATES = {"pending", "running", "stopping", "stopped", "shutting-down", "terminated"}


# ---------------------------------------------------------------- helpers
def _ec2(region: str = ""):
    return boto3.client("ec2", region_name=region or DEFAULT_REGION)


def _name_tag(instance: dict) -> str:
    for tag in instance.get("Tags", []):
        if tag["Key"] == "Name":
            return tag["Value"]
    return "(no name)"


def _aws_error(e: Exception) -> str:
    if isinstance(e, NoCredentialsError):
        return ("No AWS credentials found. Attach an IAM role to this EC2 instance "
                "(see deploy/iam/). In Docker, also set the IMDS hop limit to 2 "
                "(deploy/fix_imds_hop_limit.sh).")
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        return f"AWS error {err.get('Code')}: {err.get('Message')}"
    return f"AWS error: {e}"


def _all_instances(region: str, filters: list | None = None) -> list[dict]:
    """Return every instance (handles pagination for you)."""
    paginator = _ec2(region).get_paginator("describe_instances")
    instances = []
    for page in paginator.paginate(Filters=filters or []):
        for reservation in page["Reservations"]:
            instances.extend(reservation["Instances"])
    return instances


# ---------------------------------------------------------------- read-only tools
@mcp.tool()
def list_instances(state: str = "all", region: str = "") -> str:
    """List EC2 instances with their ID, name, type, state and IPs.

    Args:
        state: Filter by state: "running", "stopped", "pending", "stopping",
               "terminated" or "all" (default).
        region: AWS region such as "ap-south-1". Empty = default region from .env.
    """
    region = region or DEFAULT_REGION
    state = state.strip().lower()
    filters = []
    if state != "all":
        if state not in VALID_STATES:
            return f"Invalid state '{state}'. Use one of: all, {', '.join(sorted(VALID_STATES))}"
        filters = [{"Name": "instance-state-name", "Values": [state]}]

    try:
        instances = _all_instances(region, filters)
    except (BotoCoreError, ClientError) as e:
        return _aws_error(e)

    if not instances:
        return f"No instances found in {region} (state filter: {state})."

    lines = [f"{len(instances)} instance(s) in {region}:"]
    for i in instances:
        lines.append(
            f"- {i['InstanceId']} | {_name_tag(i)} | {i['InstanceType']} | "
            f"{i['State']['Name']} | private {i.get('PrivateIpAddress', '-')} | "
            f"public {i.get('PublicIpAddress', '-')}"
        )
    return "\n".join(lines)


@mcp.tool()
def describe_instance(instance_id: str, region: str = "") -> str:
    """Get detailed information about one EC2 instance.

    Args:
        instance_id: The instance ID, for example "i-0abc123def4567890".
        region: AWS region. Empty = default region from .env.
    """
    region = region or DEFAULT_REGION
    try:
        resp = _ec2(region).describe_instances(InstanceIds=[instance_id])
    except (BotoCoreError, ClientError) as e:
        return _aws_error(e)

    reservations = resp.get("Reservations", [])
    if not reservations:
        return f"Instance {instance_id} not found in {region}."
    i = reservations[0]["Instances"][0]
    sgs = ", ".join(g["GroupName"] for g in i.get("SecurityGroups", [])) or "-"
    tags = ", ".join(f"{t['Key']}={t['Value']}" for t in i.get("Tags", [])) or "-"
    return (
        f"Instance {i['InstanceId']} ({_name_tag(i)})\n"
        f"- State: {i['State']['Name']}\n"
        f"- Type: {i['InstanceType']}\n"
        f"- AMI: {i.get('ImageId')}\n"
        f"- AZ: {i.get('Placement', {}).get('AvailabilityZone')}\n"
        f"- Private IP: {i.get('PrivateIpAddress', '-')}\n"
        f"- Public IP: {i.get('PublicIpAddress', '-')}\n"
        f"- Key pair: {i.get('KeyName', '-')}\n"
        f"- Security groups: {sgs}\n"
        f"- Launched: {i.get('LaunchTime')}\n"
        f"- Tags: {tags}"
    )


@mcp.tool()
def get_instance_summary(region: str = "") -> str:
    """Count EC2 instances by state and by instance type in a region.

    Args:
        region: AWS region. Empty = default region from .env.
    """
    region = region or DEFAULT_REGION
    try:
        instances = _all_instances(region)
    except (BotoCoreError, ClientError) as e:
        return _aws_error(e)

    if not instances:
        return f"No instances in {region}."
    by_state = Counter(i["State"]["Name"] for i in instances)
    by_type = Counter(i["InstanceType"] for i in instances)
    return (
        f"EC2 summary for {region} — {len(instances)} total\n"
        f"By state: {dict(by_state)}\n"
        f"By type:  {dict(by_type)}"
    )


# ---------------------------------------------------------------- write tools (guarded)
def _write_blocked() -> str | None:
    if not ALLOW_WRITE:
        return ("Start/stop is disabled for safety. Set EC2_ALLOW_WRITE=true in .env "
                "and restart the EC2 MCP server to enable it.")
    return None


@mcp.tool()
def start_instance(instance_id: str, region: str = "") -> str:
    """Start a stopped EC2 instance. Only works if EC2_ALLOW_WRITE=true.

    Args:
        instance_id: The instance ID to start.
        region: AWS region. Empty = default region from .env.
    """
    if msg := _write_blocked():
        return msg
    try:
        resp = _ec2(region).start_instances(InstanceIds=[instance_id])
    except (BotoCoreError, ClientError) as e:
        return _aws_error(e)
    change = resp["StartingInstances"][0]
    return (f"Start requested for {instance_id}: "
            f"{change['PreviousState']['Name']} -> {change['CurrentState']['Name']}")


@mcp.tool()
def stop_instance(instance_id: str, region: str = "") -> str:
    """Stop a running EC2 instance. Only works if EC2_ALLOW_WRITE=true.

    Args:
        instance_id: The instance ID to stop.
        region: AWS region. Empty = default region from .env.
    """
    if msg := _write_blocked():
        return msg
    try:
        resp = _ec2(region).stop_instances(InstanceIds=[instance_id])
    except (BotoCoreError, ClientError) as e:
        return _aws_error(e)
    change = resp["StoppingInstances"][0]
    return (f"Stop requested for {instance_id}: "
            f"{change['PreviousState']['Name']} -> {change['CurrentState']['Name']}")


if __name__ == "__main__":
    mode = "read + start/stop" if ALLOW_WRITE else "read-only"
    print(f"🖥  EC2 MCP server running at http://{HOST}:{PORT}/mcp  "
          f"(region {DEFAULT_REGION}, {mode})")
    mcp.run(transport="streamable-http")
