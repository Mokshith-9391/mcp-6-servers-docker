#!/usr/bin/env bash
# Creates the IAM role + instance profile for the MCP EC2 instance.
# Run this from your LAPTOP / CloudShell (needs admin AWS credentials), NOT on the instance.
#   bash deploy/iam/create_role.sh               # read-only
#   bash deploy/iam/create_role.sh --with-write  # also start/stop tagged instances
set -euo pipefail
cd "$(dirname "$0")"
ROLE=mcp-ec2-agent-role

aws iam create-role --role-name "$ROLE" \
  --assume-role-policy-document file://ec2-trust-policy.json
aws iam put-role-policy --role-name "$ROLE" --policy-name mcp-ec2-readonly \
  --policy-document file://ec2-readonly-policy.json

if [ "${1:-}" = "--with-write" ]; then
  aws iam put-role-policy --role-name "$ROLE" --policy-name mcp-ec2-startstop \
    --policy-document file://ec2-startstop-policy.json
  echo "Added start/stop permission (only for instances tagged MCPManaged=true)."
fi

aws iam create-instance-profile --instance-profile-name "$ROLE"
aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
echo "✅ Instance profile '$ROLE' ready. Attach it: EC2 console -> Actions -> Security -> Modify IAM role."
