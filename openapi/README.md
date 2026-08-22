# OpenAPI

`openapi.json` 是 AidFlow API 的完整合約（由 FastAPI 產生）。重新匯出：

```bash
docker compose up -d api && bash client/export_openapi.sh
```

公開端點位於 `/v1/public/*`；其餘端點在設定 `ADMIN_API_KEY` 時需要 `X-API-Key`。
