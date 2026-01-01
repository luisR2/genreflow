#!/usr/bin/env bash

# Gracefully shut down all Raspberry Pi nodes in the k3s cluster.

# ===== CONFIGURATION =====

# List of node hostnames (which also match their SSH usernames)
NODES=(
  "k8s-master"
  "k8s-node1"
  "k8s-node2"
  "k8s-node3"
)

# Shutdown command to run on each Pi
SHUTDOWN_CMD="sudo shutdown -h now"

# ===== SCRIPT =====

echo "This script will SHUT DOWN the following Raspberry Pi nodes:"
for node in "${NODES[@]}"; do
  echo "  - $node"
done

read -p "Are you sure you want to continue? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
  echo "Aborted."
  exit 0
fi

for node in "${NODES[@]}"; do
  echo "Shutting down $node ..."
  # Username == hostname, e.g. k8s-master@k8s-master
  ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "${node}@${node}" "${SHUTDOWN_CMD}" || {
    echo "Could not shut down ${node} (SSH unreachable or node offline)."
  }
done

echo "Shutdown command sent to all nodes."
echo "Give them a few seconds to power off completely."
