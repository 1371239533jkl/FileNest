#!/bin/bash
# Smart File Manager · Web 控制台端到端验证
# 用法：上传到服务器后执行  bash verify_web.sh
# 环境变量：BASE（默认 http://127.0.0.1:8765）、SFM_API_KEY（默认读 /home/admin/sfm/api_key.txt）
# 说明：AI 相关检查依赖项目根目录的 ai_models.json；未部署时该项记为 SKIP 而非 FAIL。
BASE=${BASE:-http://127.0.0.1:8765}
KEY=${SFM_API_KEY:-$(cat /home/admin/sfm/api_key.txt 2>/dev/null | tr -d '\r\n' | sed 's/^SFM_API_KEY=//')}
AI_CONF=${AI_CONF:-/home/admin/sfm/app/ai_models.json}
PASS=0
FAIL=0
SKIP=0

chk() {  # $1=名称 $2=期望 $3=实际
  if [ "$2" = "$3" ]; then
    echo "PASS $1 ($3)"; PASS=$((PASS + 1))
  else
    echo "FAIL $1 (expect $2 got $3)"; FAIL=$((FAIL + 1))
  fi
}

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "== 静态资源 =="
chk "GET /" 200 "$(code "$BASE/")"
for f in js/app.js js/charts.js js/command.js js/views-system.js js/views-dashboard.js css/app.css; do
  chk "GET /$f" 200 "$(code "$BASE/$f")"
done

echo "== 鉴权 =="
chk "dashboard 无 Key" 401 "$(code "$BASE/api/dashboard")"
chk "dashboard 带 Key" 200 "$(code -H "X-API-Key: $KEY" "$BASE/api/dashboard")"

echo "== 仪表盘新字段 =="
body=$(curl -s -H "X-API-Key: $KEY" "$BASE/api/dashboard")
for field in classified_count coverage tag_count recent_7d unclassified_count recent_activities; do
  case "$body" in
    *"$field"*) echo "PASS 含字段 $field"; PASS=$((PASS + 1)) ;;
    *) echo "FAIL 缺字段 $field"; FAIL=$((FAIL + 1)) ;;
  esac
done

echo "== 前端装配 =="
html=$(curl -s "$BASE/")
for token in btn-collapse btn-theme btn-cmd charts.js command.js; do
  case "$html" in
    *"$token"*) echo "PASS index 含 $token"; PASS=$((PASS + 1)) ;;
    *) echo "FAIL index 缺 $token"; FAIL=$((FAIL + 1)) ;;
  esac
done

echo "== AI 模型配置接口 =="
prov=$(curl -s -H "X-API-Key: $KEY" "$BASE/api/ai/providers")
case "$prov" in
  *templates*) echo "PASS /api/ai/providers 可访问（含内置模板）"; PASS=$((PASS + 1)) ;;
  *) echo "FAIL /api/ai/providers: $(echo "$prov" | head -c 120)"; FAIL=$((FAIL + 1)) ;;
esac
chk "ai/providers 无 Key" 401 "$(code "$BASE/api/ai/providers")"

echo "== AI 流式（SSE）=="
if [ ! -f "$AI_CONF" ]; then
  echo "SKIP 流式：未部署 $AI_CONF（AI 未启用）"
  SKIP=$((SKIP + 1))
else
  stream=$(curl -s -N --max-time 90 -X POST \
    -H 'Content-Type: application/json' -H "X-API-Key: $KEY" \
    -d '{"message":"python"}' "$BASE/api/ai/chat/stream")
  if echo "$stream" | grep -qE '"type": ?"delta"'; then
    echo "PASS 流式返回 delta 分片"; PASS=$((PASS + 1))
  else
    echo "FAIL 流式无 delta: $(echo "$stream" | head -c 160)"; FAIL=$((FAIL + 1))
  fi
  if echo "$stream" | grep -qE '"type": ?"done"'; then
    echo "PASS 流式正常收尾"; PASS=$((PASS + 1))
  else
    echo "FAIL 流式未收尾"; FAIL=$((FAIL + 1))
  fi
fi

echo "== 流式鉴权 =="
chk "chat/stream 无 Key" 401 "$(code -X POST -H 'Content-Type: application/json' -d '{"message":"x"}' "$BASE/api/ai/chat/stream")"

echo "---"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP"
[ "$FAIL" -eq 0 ]
