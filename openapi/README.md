# OpenAPI

`openapi.json` 是 AidFlow API 的完整合約（由 FastAPI 產生）。重新匯出：

```bash
docker compose up -d api && bash client/export_openapi.sh
```

公開端點位於 `/v1/public/*`（免登入）；`/v1/health` 與 `/v1/line/webhook`（LINE 簽章驗證）亦免登入。
其餘政府管理後台端點需 `Authorization: Bearer <token>`（`POST /v1/auth/login` 取得），並依角色授權；
系統服務可改用 `X-API-Key`（`ADMIN_API_KEY`）。
