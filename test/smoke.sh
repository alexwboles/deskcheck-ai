#!/bin/sh
# deskcheck smoke: unit tests + CLI demo pass + denied-app negative case.
set -e
cd "$(dirname "$0")/.."
echo "== unit + e2e tests =="
python3 -m unittest discover -s tests -v 2>&1 | tail -5
echo "== CLI demo pass (MockDriver) =="
python3 -m deskcheck run examples/demo-pass.yaml \
  --config examples/config.yaml --driver mock --mock-windows demo-app \
  --out-dir /tmp/deskcheck-smoke/demo
test -f /tmp/deskcheck-smoke/demo/report.md
test -f /tmp/deskcheck-smoke/demo/report.html
test -f /tmp/deskcheck-smoke/demo/actions.jsonl
echo "== CLI denied-app must exit 1 =="
if python3 -m deskcheck run examples/denied-app.yaml \
  --config examples/config.yaml --driver mock \
  --out-dir /tmp/deskcheck-smoke/denied; then
  echo "FAIL: denied app run exited 0" >&2; exit 1
fi
echo "== MCP handshake smoke =="
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"ping"}' \
  | python3 -m deskcheck mcp | grep -q '"serverInfo"'
echo "SMOKE OK"
