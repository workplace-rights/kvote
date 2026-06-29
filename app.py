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

@app.route('/')
def index():
    return send_from_directory(STATIC, 'host.html')

@app.route('/host')
def host():
    return send_from_directory(STATIC, 'host.html')

@app.route('/vote')
def vote_page():
    return send_from_directory(STATIC, 'vote.html')

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
