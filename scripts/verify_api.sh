#!/bin/bash
# 部署验证脚本（服务器端执行）
KEY=$(grep SFM_API_KEY /home/admin/sfm/api_key.txt | cut -d= -f2)

echo "--- 1. health (no key, expect 200):"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/health

echo "--- 2. api without key (expect 401):"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/api/search

echo "--- 3. scan:"
curl -s -X POST http://127.0.0.1:8765/api/scan \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d '{"directory": "/home/admin/sfm/app", "recursive": true}'
echo

echo "--- 4. search ext=.py limit 3:"
curl -s "http://127.0.0.1:8765/api/search?ext=.py&limit=3" -H "X-API-Key: $KEY"
echo

echo "--- 5. tags:"
curl -s http://127.0.0.1:8765/api/tags -H "X-API-Key: $KEY"
echo

echo "--- 6. lifecycle check:"
curl -s http://127.0.0.1:8765/api/lifecycle/check -H "X-API-Key: $KEY"
echo
