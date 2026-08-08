#!/usr/bin/env bash
# Refresh the deployed Alliance session after an operator bootstrap.
#
#   scripts/refresh-session.sh [user@host]
#
# The bootstrap itself stays human-in-the-loop (a browser, a real login);
# this only copies the resulting session to the server with the ownership
# the API container needs.
#
# The container runs as uid 1000 (apiuser). A file owned by the host login
# user is unreadable inside the container, and the app reports
# SessionInvalid — which looks like an expired session but is not.
set -euo pipefail

TARGET="${1:-deploy@139.180.170.147}"
LOCAL="${ALLIANCE_SESSION_PATH:-$HOME/.laundryconnect/alliance-session.json}"
REMOTE="/opt/laundryconnect/alliance-session.json"
CONTAINER_UID=1000

if [ ! -f "$LOCAL" ]; then
  echo "No session at $LOCAL — run the bootstrap first:" >&2
  echo "  cd services/api && ALLIANCE_SESSION_PATH=$LOCAL \\" >&2
  echo "    uv run python -m app.providers.alliance.bootstrap" >&2
  exit 1
fi

echo "Copying session to ${TARGET}…"
# Staged through a temp path: the live file is owned by the container uid,
# so the login user cannot overwrite it directly. `cp` (not `mv`) preserves
# the destination inode, which matters because Docker bind-mounts single
# files by inode — replacing it would leave the container on the old one.
STAGE="/tmp/alliance-session.$$.json"
scp -q "$LOCAL" "${TARGET}:${STAGE}"
ssh "$TARGET" "sudo cp ${STAGE} ${REMOTE} && \
               sudo chown ${CONTAINER_UID}:${CONTAINER_UID} ${REMOTE} && \
               sudo chmod 600 ${REMOTE} && rm -f ${STAGE}"

echo "Verifying the container can read it…"
ssh "$TARGET" "sudo docker exec laundryconnect-prod-api-1 python -c '
import json, sys
try:
    data = json.load(open(\"/run/secrets/alliance-session.json\"))
    print(\"  OK -\", len(data[\"cookies\"]), \"cookies readable by the app\")
except Exception as exc:
    print(\"  FAILED:\", type(exc).__name__)
    sys.exit(1)
'"

echo "Done. The session is live; no restart needed."
