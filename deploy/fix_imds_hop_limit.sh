#!/usr/bin/env bash
# Containers reach the EC2 IAM role through the metadata service (IMDSv2).
# Docker adds one network "hop", so the hop limit must be 2.
# Run from your LAPTOP or AWS CloudShell (not needed if already 2):
#   bash deploy/fix_imds_hop_limit.sh i-0123456789abcdef0 [region]
set -euo pipefail
IID="${1:?Usage: $0 <instance-id> [region]}"
REGION="${2:-ap-south-1}"
aws ec2 modify-instance-metadata-options --region "$REGION" \
  --instance-id "$IID" --http-endpoint enabled \
  --http-tokens required --http-put-response-hop-limit 2
echo "✅ Hop limit set to 2 for $IID. On the instance run: ./mcp.sh restart"
