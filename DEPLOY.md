# 上雲部署手冊（比賽 Demo 版）

架構：**前端 → Cloudflare Workers（免費）**、**後端 + Postgres → Render（免費）**、
**防休眠 → Cloudflare Cron Worker（免費）**。全程 US$0，無信用卡。

```
使用者 ──► Cloudflare Workers（Next.js 前端）
              │  NEXT_PUBLIC_API_BASE_URL
              ▼
          Render Free（FastAPI，開機自動跑 migration）
              │            ▲
              ▼            │ 每 5 分鐘 ping /v1/health
          Render Free PG   Cloudflare Cron Worker（防休眠）
```

需要的帳號（都免費、免信用卡）：
1. [Render](https://render.com)（可用 GitHub 登入）
2. [Cloudflare](https://dash.cloudflare.com/sign-up)

---

## 步驟 0：把程式推上 GitHub

Render 從 GitHub 部署，本機未提交的變更都要先推上去：

```bash
git add -A
git commit -m "Deploy: Cloudflare + Render"
git push origin main
```

## 步驟 1：部署後端到 Render（約 10 分鐘）

1. 登入 Render → **New +** → **Blueprint** → 選 本 repo。
2. Render 會讀取 [render.yaml](./render.yaml)，自動建立
   `aidflow-api`（Docker web service）與 `aidflow-db`（免費 Postgres）。
3. 建立時會問兩個環境變數（sync: false 的那兩個）：
   - `WEB_PUBLIC_BASE_URL`：先隨便填 `https://placeholder`（步驟 2 之後回來改）
   - `OPENAI_API_KEY`：填你的金鑰（要 AI 助手/AI 草擬就填；不填也能跑）
4. 按 **Apply**，等第一次部署完成（映像建置約 5-8 分鐘）。
5. 記下服務網址，形如 `https://aidflow-api-xxxx.onrender.com`。
6. 驗證：開 `https://<你的API網址>/v1/health` 應回 `{"status":"ok",...}`。

> 免費 Postgres 建立 30 天後會過期刪除（比賽足夠）；要長期使用屆時改接 Neon。

## 步驟 2：部署前端到 Cloudflare Workers（約 5 分鐘）

```bash
cd apps/web

# 2-1 告訴前端 API 在哪（建置時內嵌）：建立 .env.production，內容一行
#     NEXT_PUBLIC_API_BASE_URL=https://<你的API網址>
echo NEXT_PUBLIC_API_BASE_URL=https://aidflow-api-xxxx.onrender.com > .env.production

# 2-2 登入 Cloudflare（開瀏覽器授權，一次性）
npx wrangler login

# 2-3 建置 + 部署
npm run cf:deploy
```

完成後會印出前端網址，形如 `https://aidflow-web.<你的帳號>.workers.dev`。

回到 Render → `aidflow-api` → Environment，把 `WEB_PUBLIC_BASE_URL`
改成這個前端網址（貼文/推播裡的入口連結會用到），儲存後服務會自動重啟。

## 步驟 3：部署防休眠 Worker（約 2 分鐘，Demo 關鍵）

Render 免費層閒置 15 分鐘會休眠，冷啟動 30-50 秒。這個 Worker 每 5 分鐘
ping 一次健康檢查，讓後端整天保持醒著：

```bash
cd deploy/keepwarm
# 先把 wrangler.jsonc 裡的 TARGET_URL 換成你的 API 網址（保留 /v1/health）
npx wrangler deploy
```

驗證：開 Worker 網址（部署時會印出）應顯示 `status=200`。

## 步驟 4：灌 Demo 資料 + 最終檢查

```bash
# 建立四筆完整示範事件（事件、元件、通報、物資志工、派工）
set API_BASE_URL=https://<你的API網址>
set WEB_BASE_URL=https://<你的前端網址>
python client/seed_demo.py
```

Demo 前 checklist：
- [ ] 前端首頁開得起來（Cloudflare URL）
- [ ] `/console/agent` 跑一次「一句話 → 平行生成」全流程
- [ ] 公開救災網站（成果卡「開啟救災網站」）地圖與資料正常
- [ ] FB / LINE 後台開啟正常
- [ ] 後端連續閒置 20 分鐘後再開仍秒回（防休眠有效）

## 疑難排解

| 症狀 | 原因/解法 |
| --- | --- |
| 前端開得起來但資料都空 | `.env.production` 的 API 網址錯了；改完要重跑 `npm run cf:deploy` |
| API 回 CORS 錯誤 | Render 環境變數 `CORS_ORIGINS` 應為 `*`（render.yaml 已預設） |
| 第一次請求很慢 | 防休眠 Worker 還沒部署或 TARGET_URL 填錯 |
| Render 建置失敗 | 看 Render Logs；本機 `docker compose build api` 可過即應可過 |
| 想回本機開發 | 一切照舊：`docker compose up --build`（雲端設定不影響本機） |
