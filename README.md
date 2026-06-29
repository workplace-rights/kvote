# 最佳貢獻獎系統 · Render.com 部署說明

## 檔案結構
```
kahoot-vote/
├── app.py
├── requirements.txt
└── static/
    ├── host.html   ← 老師投影機畫面
    └── vote.html   ← 學生手機畫面（QR掃進來）
```

## 部署步驟（Render.com 免費）

1. GitHub 新建 repo，把整個資料夾推上去
2. Render.com → New → Web Service → 選 repo
3. 設定：
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --worker-class=gthread --threads=4`
4. Deploy（約 2 分鐘）

## 上課使用流程

1. 老師開 `https://你的網址/host` → 投影到大螢幕
2. 輸入組數 → 按「建立活動」→ 出現 QR Code
3. 各組代表用手機掃 QR → 選自己是哪組 → 加入
4. 老師畫面即時顯示哪些組已加入（綠色）
5. 老師按「開始投票」
6. 學生手機自動跳出投票選項 → 選出最佳組
7. 老師畫面即時看票數跳動
8. 老師按「公布結果」→ 大螢幕放煙火動畫 🎉
9. 下一輪按「重設」

## 注意
- Render 免費方案閒置 15 分鐘後休眠，第一次訪問等 30 秒
- 同一組只能一台手機加入（防重複靠後端 DB，不是 localStorage）
- SSE 即時同步，不需要手動刷新
