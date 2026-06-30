from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import sqlite3, json, queue, threading, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE_DIR, 'static')

app = Flask(__name__)
CORS(app)
DB = os.path.join(BASE_DIR, 'vote.db')

_subscribers = []
_sub_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS room (
                id INTEGER PRIMARY KEY CHECK(id=1),
                total_groups INTEGER DEFAULT 0,
                status TEXT DEFAULT 'waiting',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS participants (
                group_name TEXT PRIMARY KEY,
                joined_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS votes (
                voter_group TEXT PRIMARY KEY,
                voted_for TEXT NOT NULL,
                voted_at TEXT DEFAULT (datetime('now','localtime'))
            );
        ''')
        db.execute('INSERT OR IGNORE INTO room(id) VALUES(1)')

init_db()

def broadcast(event, data):
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with _sub_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(msg)
            except:
                dead.append(q)
        for q in dead:
            _subscribers.remove(q)

def get_state():
    with get_db() as db:
        room = dict(db.execute('SELECT * FROM room WHERE id=1').fetchone())
        parts = [r['group_name'] for r in db.execute('SELECT group_name FROM participants ORDER BY joined_at').fetchall()]
        votes = {r['voter_group']: r['voted_for'] for r in db.execute('SELECT voter_group, voted_for FROM votes').fetchall()}
        tally = {g: 0 for g in parts}
        for vf in votes.values():
            if vf in tally:
                tally[vf] += 1
        voted_groups = list(votes.keys())
        not_voted = [g for g in parts if g not in voted_groups]
    return {
        'status': room['status'],
        'total_groups': room['total_groups'],
        'participants': parts,
        'tally': tally,
        'voted': voted_groups,
        'not_voted': not_voted,
    }

HOST_HTML = '<!DOCTYPE html>\n<html lang="zh-TW">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>最佳貢獻獎 · 老師主持</title>\n<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\n:root{--bg:#0d0d1a;--card:#1a1a2e;--accent:#7c3aed;--green:#16a34a;--yellow:#d97706;--text:#f0f0ff;--muted:#8888aa}\nbody{font-family:\'Microsoft JhengHei\',Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}\n\n#setup-screen{display:flex;align-items:center;justify-content:center;min-height:100vh}\n.setup-card{background:var(--card);border-radius:20px;padding:40px;max-width:420px;width:90%;text-align:center;border:1px solid #2a2a4a}\n.setup-card h1{font-size:26px;margin-bottom:8px}\n.setup-card .sub{color:var(--muted);font-size:15px;margin-bottom:32px}\n.setup-card label{font-size:14px;color:var(--muted);display:block;margin-bottom:6px;text-align:left}\n.setup-card input{width:100%;padding:12px 16px;border-radius:10px;border:1px solid #3a3a5a;background:#12122a;color:var(--text);font-size:16px;font-family:inherit;margin-bottom:16px}\n.setup-card input:focus{outline:none;border-color:var(--accent)}\n.btn-start{width:100%;padding:14px;border-radius:12px;border:none;background:var(--accent);color:#fff;font-size:17px;font-weight:600;cursor:pointer;font-family:inherit;transition:all 0.15s}\n.btn-start:hover{background:#6d28d9}\n\n#waiting-screen{display:none;min-height:100vh;padding:24px}\n.w-layout{display:grid;grid-template-columns:1fr 340px;gap:24px;max-width:1100px;margin:0 auto}\n.w-side{display:flex;flex-direction:column;gap:16px}\n.phase-title{font-size:13px;letter-spacing:2px;text-transform:uppercase;color:var(--accent);margin-bottom:8px}\n.big-title{font-size:32px;font-weight:700;margin-bottom:24px}\n.qr-card{background:var(--card);border-radius:16px;padding:20px;text-align:center;border:1px solid #2a2a4a}\n.qr-card h3{font-size:14px;color:var(--muted);margin-bottom:4px}\n.qr-url{font-size:11px;color:#6666aa;margin-top:8px;word-break:break-all}\n#qr-box{background:#fff;border-radius:12px;padding:10px;display:inline-block;margin:10px 0}\n.groups-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin-top:8px}\n.g-tile{border-radius:12px;padding:14px;text-align:center;font-size:15px;font-weight:500;border:2px solid transparent;transition:all 0.3s}\n.g-tile.joined{background:#16423a;border-color:#16a34a;color:#4ade80;animation:pop-in 0.3s ease}\n.g-tile.waiting{background:#1a1a2e;border-color:#2a2a4a;color:#555577}\n@keyframes pop-in{from{transform:scale(0.8);opacity:0}to{transform:scale(1);opacity:1}}\n.stat-bar{background:var(--card);border-radius:12px;padding:16px;border:1px solid #2a2a4a}\n.stat-bar .label{font-size:13px;color:var(--muted);margin-bottom:4px}\n.stat-bar .val{font-size:28px;font-weight:700}\n.stat-bar .val span{font-size:16px;color:var(--muted)}\n.action-btn{width:100%;padding:14px;border-radius:12px;border:none;font-size:16px;font-weight:600;cursor:pointer;font-family:inherit;transition:all 0.2s}\n.btn-green{background:#16a34a;color:#fff}\n.btn-green:hover{background:#15803d}\n.btn-green:disabled{background:#2a3a2a;color:#666;cursor:not-allowed}\n.btn-yellow{background:#d97706;color:#fff}\n.btn-yellow:hover{background:#b45309}\n.btn-ghost{background:transparent;color:var(--muted);border:1px solid #3a3a5a}\n.btn-ghost:hover{border-color:#6666aa;color:var(--text)}\n\n#voting-screen{display:none;min-height:100vh;padding:24px}\n.v-layout{display:grid;grid-template-columns:1fr 300px;gap:24px;max-width:1100px;margin:0 auto}\n.live-bars{display:flex;flex-direction:column;gap:12px;margin-top:8px}\n.bar-row{display:flex;align-items:center;gap:12px}\n.bar-label{width:80px;font-size:14px;text-align:right;flex-shrink:0}\n.bar-track{flex:1;height:36px;background:#1a1a2e;border-radius:8px;overflow:hidden;border:1px solid #2a2a4a}\n.bar-fill{height:100%;border-radius:8px;display:flex;align-items:center;padding-left:12px;font-weight:600;font-size:15px;transition:width 0.5s ease}\n.not-voted-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}\n.nv-chip{padding:6px 14px;border-radius:8px;font-size:13px;background:#2a1a1a;border:1px solid #5a2a2a;color:#ff8888}\n\n#revealed-screen{display:none;min-height:100vh;padding:24px;text-align:center}\n.winner-wrap{max-width:600px;margin:0 auto;padding-top:60px}\n.trophy{font-size:80px;margin-bottom:16px;animation:trophy-bounce 0.6s ease}\n@keyframes trophy-bounce{0%{transform:scale(0) rotate(-20deg)}60%{transform:scale(1.2) rotate(5deg)}100%{transform:scale(1) rotate(0)}}\n.winner-name{font-size:52px;font-weight:700;margin-bottom:8px;background:linear-gradient(135deg,#fbbf24,#f59e0b,#d97706);-webkit-background-clip:text;-webkit-text-fill-color:transparent}\n.winner-votes{font-size:20px;color:var(--muted);margin-bottom:40px}\n.final-bars{max-width:500px;margin:0 auto 40px;display:flex;flex-direction:column;gap:10px}\n.final-bar-row{display:flex;align-items:center;gap:10px}\n.final-bar-label{width:80px;text-align:right;font-size:14px;flex-shrink:0}\n.final-bar-track{flex:1;height:28px;background:#1a1a2e;border-radius:6px;overflow:hidden}\n.final-bar-fill{height:100%;border-radius:6px;display:flex;align-items:center;padding-left:10px;font-size:13px;font-weight:600}\n.bar-gold{background:linear-gradient(90deg,#d97706,#fbbf24)}\n.bar-silver{background:#4a5568}\n.bar-normal{background:#3a3a5a}\n.confetti-piece{position:fixed;width:10px;height:10px;border-radius:2px;animation:confetti-fall linear forwards;pointer-events:none;z-index:999}\n@keyframes confetti-fall{0%{transform:translateY(-20px) rotate(0);opacity:1}100%{transform:translateY(100vh) rotate(720deg);opacity:0}}\n</style>\n</head>\n<body>\n\n<div id="setup-screen">\n  <div class="setup-card">\n    <div style="font-size:48px;margin-bottom:12px">🏆</div>\n    <h1>最佳貢獻獎</h1>\n    <p class="sub">老師主持畫面</p>\n    <label>本次共幾組？</label>\n    <input type="number" id="group-count" min="2" max="20" value="5" placeholder="輸入組數">\n    <button class="btn-start" onclick="setupRoom()">建立活動 →</button>\n  </div>\n</div>\n\n<div id="waiting-screen">\n  <div class="w-layout">\n    <div class="w-main">\n      <div class="phase-title">📡 等待加入</div>\n      <div class="big-title">請掃 QR Code 加入</div>\n      <div class="groups-grid" id="groups-grid"></div>\n    </div>\n    <div class="w-side">\n      <div class="qr-card">\n        <h3>學生掃這裡</h3>\n        <div id="qr-box"></div>\n        <div class="qr-url" id="qr-url-text"></div>\n      </div>\n      <div class="stat-bar">\n        <div class="label">已加入</div>\n        <div class="val"><span id="joined-count">0</span> <span>/ <span id="total-count">?</span> 組</span></div>\n      </div>\n      <button class="action-btn btn-green" id="start-btn" onclick="startVote()" disabled>🗳 開始投票</button>\n      <button class="action-btn btn-ghost" onclick="resetRoom()">↺ 重設 / 換組數</button>\n    </div>\n  </div>\n</div>\n\n<div id="voting-screen">\n  <div class="v-layout">\n    <div>\n      <div class="phase-title">🗳 投票進行中</div>\n      <div class="big-title" style="margin-bottom:20px">即時票數</div>\n      <div class="live-bars" id="live-bars"></div>\n    </div>\n    <div style="display:flex;flex-direction:column;gap:16px">\n      <div style="background:var(--card);border-radius:12px;padding:16px;border:1px solid #2a2a4a">\n        <div style="font-size:13px;color:var(--muted);margin-bottom:10px">⏳ 尚未投票</div>\n        <div class="not-voted-list" id="not-voted-list"></div>\n      </div>\n      <div class="stat-bar">\n        <div class="label">投票進度</div>\n        <div class="val"><span id="voted-count">0</span> <span>/ <span id="voting-total">?</span></span></div>\n      </div>\n      <button class="action-btn btn-yellow" onclick="reveal()">📊 公布結果</button>\n      <button class="action-btn btn-ghost" onclick="resetRoom()">↺ 重設 / 換組數</button>\n    </div>\n  </div>\n</div>\n\n<div id="revealed-screen">\n  <div class="winner-wrap">\n    <div class="trophy">🏆</div>\n    <div class="winner-name" id="winner-name">—</div>\n    <div class="winner-votes" id="winner-votes"></div>\n    <div class="final-bars" id="final-bars"></div>\n    <button class="action-btn btn-ghost" style="max-width:300px;margin:0 auto" onclick="resetRoom()">↺ 再來一輪</button>\n  </div>\n</div>\n\n<script>\nlet state = null;\nlet es = null;\nlet qrGenerated = false;\nconst VOTE_URL = location.origin + \'/vote\';\n\nfunction showScreen(name) {\n  [\'setup\',\'waiting\',\'voting\',\'revealed\'].forEach(s => {\n    document.getElementById(s+\'-screen\').style.display = \'none\';\n  });\n  document.getElementById(name+\'-screen\').style.display =\n    name === \'setup\' ? \'flex\' : \'block\';\n}\n\nfunction setupRoom(){\n  const n = parseInt(document.getElementById(\'group-count\').value);\n  if(n < 2 || n > 20){ alert(\'請輸入 2-20 之間的組數\'); return; }\n  fetch(\'/api/setup\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({total_groups:n})})\n    .then(r=>r.json()).then(d=>{\n      if(d.ok){ qrGenerated = false; connectSSE(); }\n    });\n}\n\nfunction connectSSE(){\n  if(es){ es.close(); es = null; }\n  es = new EventSource(\'/api/events\');\n  es.addEventListener(\'state\', e => {\n    state = JSON.parse(e.data);\n    render();\n  });\n  es.onerror = () => { setTimeout(connectSSE, 3000); es.close(); es = null; };\n}\n\nfunction render(){\n  if(!state) return;\n  const s = state.status;\n  if(s === \'waiting\') { showScreen(\'waiting\'); renderWaiting(); }\n  else if(s === \'voting\') { showScreen(\'voting\'); renderVoting(); }\n  else if(s === \'revealed\') { showScreen(\'revealed\'); renderRevealed(); }\n}\n\nfunction renderWaiting(){\n  if(!qrGenerated){\n    document.getElementById(\'qr-box\').innerHTML = \'\';\n    new QRCode(document.getElementById(\'qr-box\'),{\n      text: VOTE_URL, width:180, height:180,\n      colorDark:\'#1a1a18\', colorLight:\'#ffffff\',\n      correctLevel: QRCode.CorrectLevel.M\n    });\n    document.getElementById(\'qr-url-text\').textContent = VOTE_URL;\n    qrGenerated = true;\n  }\n  const {total_groups, participants} = state;\n  const groups = Array.from({length:total_groups},(_,i)=>`第${i+1}組`);\n  document.getElementById(\'groups-grid\').innerHTML = groups.map(g => {\n    const joined = participants.includes(g);\n    return `<div class="g-tile ${joined?\'joined\':\'waiting\'}">${joined?\'✅ \':\'⬜ \'}${g}</div>`;\n  }).join(\'\');\n  document.getElementById(\'joined-count\').textContent = participants.length;\n  document.getElementById(\'total-count\').textContent = total_groups;\n  document.getElementById(\'start-btn\').disabled = participants.length < 2;\n}\n\nconst BAR_COLORS = [\'#7c3aed\',\'#2563eb\',\'#059669\',\'#d97706\',\'#dc2626\',\'#db2777\',\'#0891b2\',\'#65a30d\'];\n\nfunction renderVoting(){\n  const {participants, tally, not_voted} = state;\n  const maxVotes = Math.max(...Object.values(tally), 1);\n  document.getElementById(\'live-bars\').innerHTML = participants.map((g,i) => {\n    const v = tally[g]||0;\n    const pct = Math.round(v/maxVotes*100);\n    return `<div class="bar-row">\n      <div class="bar-label">${g}</div>\n      <div class="bar-track">\n        <div class="bar-fill" style="width:${Math.max(pct,v>0?6:0)}%;background:${BAR_COLORS[i%BAR_COLORS.length]}">${v>0?v:\'\'}</div>\n      </div>\n    </div>`;\n  }).join(\'\');\n  document.getElementById(\'not-voted-list\').innerHTML = not_voted.length\n    ? not_voted.map(g=>`<div class="nv-chip">${g}</div>`).join(\'\')\n    : \'<span style="color:#4ade80;font-size:13px">✅ 全員已投票！</span>\';\n  document.getElementById(\'voted-count\').textContent = state.voted.length;\n  document.getElementById(\'voting-total\').textContent = participants.length;\n}\n\nfunction renderRevealed(){\n  const {participants, tally} = state;\n  const sorted = [...participants].sort((a,b)=>(tally[b]||0)-(tally[a]||0));\n  const winner = sorted[0];\n  document.getElementById(\'winner-name\').textContent = winner;\n  document.getElementById(\'winner-votes\').textContent = `獲得 ${tally[winner]||0} 票 🎉`;\n  document.getElementById(\'final-bars\').innerHTML = sorted.map((g,i) => {\n    const v = tally[g]||0;\n    const pct = (tally[winner]||1) ? Math.round(v/(tally[winner]||1)*100) : 0;\n    const cls = i===0?\'bar-gold\':i===1?\'bar-silver\':\'bar-normal\';\n    return `<div class="final-bar-row">\n      <div class="final-bar-label">${[\'🥇\',\'🥈\',\'🥉\'][i]||\'\u3000\'}${g}</div>\n      <div class="final-bar-track">\n        <div class="final-bar-fill ${cls}" style="width:${Math.max(pct,4)}%">${v} 票</div>\n      </div>\n    </div>`;\n  }).join(\'\');\n  launchConfetti();\n}\n\nfunction launchConfetti(){\n  const colors=[\'#fbbf24\',\'#f87171\',\'#34d399\',\'#60a5fa\',\'#c084fc\',\'#fb923c\'];\n  for(let i=0;i<80;i++){\n    const el=document.createElement(\'div\');\n    el.className=\'confetti-piece\';\n    el.style.cssText=`left:${Math.random()*100}vw;top:-20px;background:${colors[Math.floor(Math.random()*colors.length)]};animation-duration:${1.5+Math.random()*2}s;animation-delay:${Math.random()*0.8}s;width:${6+Math.random()*10}px;height:${6+Math.random()*10}px`;\n    document.body.appendChild(el);\n    setTimeout(()=>el.remove(),4000);\n  }\n}\n\nfunction startVote(){ fetch(\'/api/start\',{method:\'POST\'}); }\nfunction reveal(){ fetch(\'/api/reveal\',{method:\'POST\'}); }\n\nfunction resetRoom(){\n  if(!confirm(\'確定重設？所有資料將清除\')) return;\n  if(es){ es.close(); es = null; }\n  fetch(\'/api/reset\',{method:\'POST\'}).then(()=>{\n    state = null;\n    qrGenerated = false;\n    showScreen(\'setup\');\n  });\n}\n\n// 頁面載入時一律連接 SSE，讓畫面自動同步\nconnectSSE();\n</script>\n</body>\n</html>\n'
VOTE_HTML = '<!DOCTYPE html>\n<html lang="zh-TW">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">\n<title>最佳貢獻獎 · 投票</title>\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\nbody{font-family:\'Microsoft JhengHei\',Arial,sans-serif;background:#0d0d1a;color:#f0f0ff;min-height:100vh;display:flex;flex-direction:column}\n.topbar{background:#1a1a2e;padding:16px 20px;border-bottom:1px solid #2a2a4a;text-align:center}\n.topbar h1{font-size:17px;font-weight:600}\n.topbar .sub{font-size:12px;color:#8888aa;margin-top:2px}\n.container{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px 16px;max-width:480px;margin:0 auto;width:100%}\n.card{background:#1a1a2e;border-radius:16px;padding:24px;width:100%;border:1px solid #2a2a4a;margin-bottom:16px}\n.section-title{font-size:15px;font-weight:600;margin-bottom:16px}\n.info-text{font-size:13px;color:#8888aa;margin-bottom:14px}\n.group-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}\n.group-btn{padding:16px 8px;border-radius:12px;border:2px solid #2a2a4a;background:#12122a;color:#f0f0ff;font-size:15px;font-weight:500;cursor:pointer;font-family:inherit;text-align:center;transition:all 0.15s;-webkit-tap-highlight-color:transparent}\n.group-btn:active{transform:scale(0.95)}\n.group-btn.selected{background:#7c3aed;border-color:#7c3aed;color:#fff}\n.group-btn.taken{opacity:0.35;cursor:not-allowed;border-color:#3a2a2a;background:#1a0a0a}\n.vote-grid{display:flex;flex-direction:column;gap:10px}\n.vote-btn{padding:18px 20px;border-radius:12px;border:2px solid #2a2a4a;background:#12122a;color:#f0f0ff;font-size:16px;font-weight:500;cursor:pointer;font-family:inherit;text-align:left;transition:all 0.15s;-webkit-tap-highlight-color:transparent;display:flex;align-items:center;gap:12px}\n.vote-btn:active{transform:scale(0.98)}\n.vote-btn.selected{border-color:#7c3aed;background:#3b1f6e}\n.vote-btn.own{opacity:0.3;cursor:not-allowed;background:#1a0a0a;border-color:#3a1a1a}\n.vote-radio{width:22px;height:22px;border-radius:50%;border:2px solid #4a4a6a;flex-shrink:0;display:flex;align-items:center;justify-content:center}\n.vote-btn.selected .vote-radio{background:#7c3aed;border-color:#7c3aed}\n.vote-radio::after{content:\'\';width:8px;height:8px;border-radius:50%;background:#fff;display:none}\n.vote-btn.selected .vote-radio::after{display:block}\n.btn-confirm{width:100%;padding:16px;border-radius:12px;border:none;background:#7c3aed;color:#fff;font-size:17px;font-weight:600;cursor:pointer;font-family:inherit;margin-top:4px;transition:all 0.15s}\n.btn-confirm:disabled{background:#2a2a4a;color:#666;cursor:not-allowed}\n.btn-confirm:not(:disabled):active{transform:scale(0.98);background:#6d28d9}\n.state-box{text-align:center;padding:20px 0;width:100%}\n.state-icon{font-size:64px;margin-bottom:16px}\n.state-title{font-size:20px;font-weight:600;margin-bottom:8px}\n.state-sub{font-size:14px;color:#8888aa;line-height:1.6}\n.pulse{animation:pulse 1.5s ease-in-out infinite}\n@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}\n</style>\n</head>\n<body>\n<div class="topbar">\n  <h1>🏆 最佳貢獻獎</h1>\n  <div class="sub" id="topbar-sub">連線中...</div>\n</div>\n<div class="container" id="main">\n  <div class="state-box">\n    <div class="state-icon pulse">⏳</div>\n    <div class="state-title">連線中...</div>\n  </div>\n</div>\n\n<script>\nlet myGroup = null, hasJoined = false, hasVoted = false, currentState = null;\nwindow._selectedVote = null;\n\nfunction connectSSE(){\n  const es = new EventSource(\'/api/events\');\n  es.addEventListener(\'state\', e => {\n    currentState = JSON.parse(e.data);\n    render();\n  });\n  es.onerror = () => { setTimeout(connectSSE, 3000); es.close(); };\n}\n\nfunction render(){\n  const s = currentState;\n  if(!s) return;\n\n  // 若老師重設，學生狀態也跟著重置\n  if(s.status === \'waiting\' && s.participants.length === 0 && (hasJoined || hasVoted)){\n    hasJoined = false;\n    hasVoted = false;\n    myGroup = null;\n    window._selectedVote = null;\n  }\n\n  document.getElementById(\'topbar-sub\').textContent =\n    s.status===\'waiting\' ? \'⏳ 等待老師開始\' :\n    s.status===\'voting\'  ? \'🗳 投票進行中\' :\n    s.status===\'revealed\'? \'🏆 結果公布\' : \'\';\n\n  if(hasVoted){\n    if(s.status === \'revealed\') renderDoneRevealed(s);\n    else showMsg(\'✅\',\'已送出投票！\',\'等待老師公布結果...\');\n    return;\n  }\n\n  if(s.status === \'waiting\'){\n    if(!hasJoined) renderJoin(s);\n    else showWaitingJoined();\n  } else if(s.status === \'voting\'){\n    if(!hasJoined){ showMsg(\'⚠️\',\'加入太晚了\',\'投票已開始，請下次早點加入\'); return; }\n    renderVote(s);\n  } else if(s.status === \'revealed\'){\n    renderDoneRevealed(s);\n  }\n}\n\nfunction showMsg(icon, title, sub){\n  document.getElementById(\'main\').innerHTML =\n    `<div class="state-box"><div class="state-icon">${icon}</div><div class="state-title">${title}</div><div class="state-sub">${sub}</div></div>`;\n}\n\nfunction renderJoin(s){\n  if(!s.total_groups || s.total_groups === 0){\n    showMsg(\'⏳\',\'等待老師設定\',\'請稍候...\');\n    return;\n  }\n  const groups = Array.from({length:s.total_groups},(_,i)=>`第${i+1}組`);\n  document.getElementById(\'main\').innerHTML = `\n    <div class="card">\n      <div class="section-title">👋 我是...</div>\n      <div class="info-text">選擇你的組別（每組限一台手機）</div>\n      <div class="group-grid" id="group-grid">\n        ${groups.map(g => {\n          const taken = s.participants.includes(g);\n          return `<button class="group-btn ${taken?\'taken\':\'\'}" data-g="${g}" ${taken?\'disabled\':\'\'}>${g}${taken?\' ✓\':\'\'}</button>`;\n        }).join(\'\')}\n      </div>\n    </div>\n    <button class="btn-confirm" id="join-btn" onclick="doJoin()" disabled>加入活動</button>`;\n  document.querySelectorAll(\'.group-btn:not([disabled])\').forEach(btn => {\n    btn.onclick = () => {\n      myGroup = btn.dataset.g;\n      document.querySelectorAll(\'.group-btn\').forEach(b => b.classList.remove(\'selected\'));\n      btn.classList.add(\'selected\');\n      document.getElementById(\'join-btn\').disabled = false;\n    };\n  });\n}\n\nfunction doJoin(){\n  if(!myGroup) return;\n  const btn = document.getElementById(\'join-btn\');\n  btn.disabled = true; btn.textContent = \'加入中...\';\n  fetch(\'/api/join\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({group:myGroup})})\n    .then(r=>r.json()).then(d=>{\n      if(d.ok){ hasJoined = true; render(); }\n      else if(d.already_joined){ alert(\'此組已有人加入，請選其他組\'); myGroup = null; btn.disabled = false; btn.textContent = \'加入活動\'; }\n      else { alert(d.error||\'加入失敗\'); btn.disabled = false; btn.textContent = \'加入活動\'; }\n    });\n}\n\nfunction showWaitingJoined(){\n  document.getElementById(\'main\').innerHTML = `\n    <div class="state-box">\n      <div class="state-icon pulse">⏳</div>\n      <div class="state-title">${myGroup} 已加入！</div>\n      <div class="state-sub">等待老師開始投票...<br><br>請把手機畫面保持開啟</div>\n    </div>`;\n}\n\nfunction renderVote(s){\n  window._selectedVote = null;\n  document.getElementById(\'main\').innerHTML = `\n    <div class="card">\n      <div class="section-title">🗳 選出最佳貢獻獎</div>\n      <div class="info-text">你是 <strong>${myGroup}</strong>，選出表現最佳的組別</div>\n      <div class="vote-grid">\n        ${s.participants.map(g => {\n          const isOwn = g === myGroup;\n          return `<button class="vote-btn ${isOwn?\'own\':\'\'}" data-g="${g}" ${isOwn?\'disabled\':\'\'}>\n            <div class="vote-radio"></div>\n            <span>${g}${isOwn?\' （自己）\':\'\'}</span>\n          </button>`;\n        }).join(\'\')}\n      </div>\n    </div>\n    <button class="btn-confirm" id="vote-btn" onclick="doVote()" disabled>確認投票</button>`;\n  document.querySelectorAll(\'.vote-btn:not([disabled])\').forEach(btn => {\n    btn.onclick = () => {\n      window._selectedVote = btn.dataset.g;\n      document.querySelectorAll(\'.vote-btn\').forEach(b => b.classList.remove(\'selected\'));\n      btn.classList.add(\'selected\');\n      document.getElementById(\'vote-btn\').disabled = false;\n    };\n  });\n}\n\nfunction doVote(){\n  const v = window._selectedVote;\n  if(!v) return;\n  const btn = document.getElementById(\'vote-btn\');\n  btn.disabled = true; btn.textContent = \'送出中...\';\n  fetch(\'/api/submit\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({voter_group:myGroup,voted_for:v})})\n    .then(r=>r.json()).then(d=>{\n      if(d.ok){ hasVoted = true; render(); }\n      else{ btn.disabled = false; btn.textContent = \'確認投票\'; alert(d.error||\'送出失敗\'); }\n    });\n}\n\nfunction renderDoneRevealed(s){\n  const sorted = [...s.participants].sort((a,b)=>(s.tally[b]||0)-(s.tally[a]||0));\n  const winner = sorted[0];\n  document.getElementById(\'main\').innerHTML = `\n    <div class="state-box">\n      <div class="state-icon">🏆</div>\n      <div class="state-title">${winner}</div>\n      <div class="state-sub">榮獲最佳貢獻獎！<br>${s.tally[winner]||0} 票</div>\n    </div>\n    <div class="card" style="margin-top:8px">\n      <div style="font-size:13px;color:#8888aa;margin-bottom:10px">最終結果</div>\n      ${sorted.map((g,i)=>`\n        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #2a2a4a;font-size:14px">\n          <span>${[\'🥇\',\'🥈\',\'🥉\'][i]||\'\u3000\'} ${g}</span>\n          <span style="color:#fbbf24;font-weight:600">${s.tally[g]||0} 票</span>\n        </div>`).join(\'\')}\n    </div>`;\n}\n\nconnectSSE();\n</script>\n</body>\n</html>\n'

@app.route('/')
def index():
    return HOST_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/host')
def host():
    return HOST_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/vote')
def vote_page():
    return VOTE_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/api/events')
def sse():
    q = queue.Queue(maxsize=50)
    with _sub_lock:
        _subscribers.append(q)
    def stream():
        state = get_state()
        yield f"event: state\ndata: {json.dumps(state, ensure_ascii=False)}\n\n"
        while True:
            try:
                msg = q.get(timeout=25)
                yield msg
            except queue.Empty:
                yield ": ping\n\n"
    return Response(stream(), mimetype='text/event-stream',
                    headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.route('/api/setup', methods=['POST'])
def setup():
    data = request.json
    n = int(data.get('total_groups', 5))
    if n < 2 or n > 20:
        return jsonify({'error': '組數需在 2-20 之間'}), 400
    with get_db() as db:
        db.execute('UPDATE room SET total_groups=?, status="waiting", created_at=datetime("now","localtime") WHERE id=1', (n,))
        db.execute('DELETE FROM participants')
        db.execute('DELETE FROM votes')
    broadcast('state', get_state())
    return jsonify({'ok': True})

@app.route('/api/start', methods=['POST'])
def start_vote():
    with get_db() as db:
        db.execute('UPDATE room SET status="voting" WHERE id=1')
    broadcast('state', get_state())
    return jsonify({'ok': True})

@app.route('/api/reveal', methods=['POST'])
def reveal():
    with get_db() as db:
        db.execute('UPDATE room SET status="revealed" WHERE id=1')
    broadcast('state', get_state())
    return jsonify({'ok': True})

@app.route('/api/reset', methods=['POST'])
def reset():
    with get_db() as db:
        db.execute('UPDATE room SET status="waiting" WHERE id=1')
        db.execute('DELETE FROM participants')
        db.execute('DELETE FROM votes')
    broadcast('state', get_state())
    return jsonify({'ok': True})

@app.route('/api/state')
def state():
    return jsonify(get_state())

@app.route('/api/join', methods=['POST'])
def join():
    data = request.json
    group = data.get('group', '').strip()
    with get_db() as db:
        room = dict(db.execute('SELECT * FROM room WHERE id=1').fetchone())
        if room['status'] == 'revealed':
            return jsonify({'error': '活動已結束'}), 403
        n = room['total_groups']
        valid = [f'第{i+1}組' for i in range(n)]
        if group not in valid:
            return jsonify({'error': '無效的組別'}), 400
        existing = db.execute('SELECT group_name FROM participants WHERE group_name=?', (group,)).fetchone()
        if existing:
            return jsonify({'error': '此組已有人加入', 'already_joined': True}), 409
        db.execute('INSERT OR IGNORE INTO participants(group_name) VALUES(?)', (group,))
    broadcast('state', get_state())
    return jsonify({'ok': True})

@app.route('/api/submit', methods=['POST'])
def submit():
    data = request.json
    voter = data.get('voter_group', '').strip()
    voted_for = data.get('voted_for', '').strip()
    with get_db() as db:
        room = dict(db.execute('SELECT * FROM room WHERE id=1').fetchone())
        if room['status'] != 'voting':
            return jsonify({'error': '目前不在投票階段'}), 403
        parts = [r['group_name'] for r in db.execute('SELECT group_name FROM participants').fetchall()]
        if voter not in parts:
            return jsonify({'error': '請先加入活動'}), 400
        if voted_for not in parts or voted_for == voter:
            return jsonify({'error': '無效的投票對象'}), 400
        existing = db.execute('SELECT voter_group FROM votes WHERE voter_group=?', (voter,)).fetchone()
        if existing:
            return jsonify({'error': '您已投過票'}), 409
        db.execute('INSERT INTO votes(voter_group, voted_for) VALUES(?,?)', (voter, voted_for))
    broadcast('state', get_state())
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(debug=True, port=5001, threaded=True)
