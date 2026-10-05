import os, re, time, random, sqlite3, json, urllib.request, urllib.parse, urllib.error
from flask import Flask, request, jsonify, session, g, send_from_directory, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=5184000)
DB = os.environ.get("DB_PATH", "data.db")  # Railway: Volume mount /data + DB_PATH=/data/data.db
METHODS = ["bKash", "Nagad", "Rocket", "Binance", "Bybit"]
WHEEL = [5, 7, 10, 12, 15, 25, 8, 20]
DEF = {"site": "TOPUP BD", "telegram": "", "popup": "", "min_withdraw": "50",
       "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""), "auto_topup": "off", "sup_url": os.environ.get("SUPPLIER_URL", ""),
       "sup_key": os.environ.get("SUPPLIER_KEY", ""), "sup_header": "Authorization", "sup_prefix": "Bearer ",
       "sup_body": '{"player_id":"{uid}","product":"{code}","reference":"{order_id}"}', "sup_ok_field": "status", "sup_ok_value": "success",
       "sup_fail_values": "failed,error,rejected,cancelled"}
for _m in METHODS: DEF["pay_" + _m] = ""

class E(Exception):
    def __init__(s, m, c=400): s.m, s.c = m, c
@app.errorhandler(E)
def _e(e): return jsonify(error=e.m), e.c

def db():
    if "d" not in g:
        g.d = sqlite3.connect(DB); g.d.row_factory = sqlite3.Row
    return g.d
@app.teardown_appcontext
def _close(_):
    d = g.pop("d", None)
    if d: d.close()
def q(sql, a=(), one=False):
    d = db(); r = d.execute(sql, a).fetchall(); d.commit()
    return (dict(r[0]) if r else None) if one else [dict(x) for x in r]
def run(sql, a=()):
    d = db(); n = d.execute(sql, a).rowcount; d.commit(); return n
def credit(uid, amt): run("UPDATE users SET balance=balance+? WHERE id=?", (amt, uid))
def S():
    s = dict(DEF); s.update({r["k"]: r["v"] for r in q("SELECT * FROM settings")}); return s

def init():
    with app.app_context():
        d = db()
        d.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, pw TEXT, balance REAL DEFAULT 0,
          coins INTEGER DEFAULT 0, last_spin TEXT, is_admin INTEGER DEFAULT 0, banned INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS packages(id INTEGER PRIMARY KEY, game TEXT, name TEXT, price REAL);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY, user_id INT, method TEXT, trx TEXT UNIQUE, amount REAL, status TEXT DEFAULT 'pending', created TEXT);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INT, package TEXT, player_id TEXT, price REAL, status TEXT DEFAULT 'pending', created TEXT);
        CREATE TABLE IF NOT EXISTS withdrawals(id INTEGER PRIMARY KEY, user_id INT, method TEXT, account TEXT, amount REAL, status TEXT DEFAULT 'pending', created TEXT);
        CREATE TABLE IF NOT EXISTS tournaments(id INTEGER PRIMARY KEY, title TEXT, mode TEXT, prize REAL, entry REAL, per_kill REAL,
          min_level INT, slots INT, start TEXT, room_id TEXT DEFAULT '', room_pass TEXT DEFAULT '', status TEXT DEFAULT 'open');
        CREATE TABLE IF NOT EXISTS joins(id INTEGER PRIMARY KEY, tid INT, user_id INT, ign TEXT, UNIQUE(tid,user_id));
        CREATE TABLE IF NOT EXISTS spins(id INTEGER PRIMARY KEY, user_id INT, coins INT, created TEXT);
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);""")
        for t_, c_ in [("packages", "code TEXT DEFAULT ''"), ("orders", "note TEXT DEFAULT ''"), ("users", "email TEXT")]:
            try: d.execute(f"ALTER TABLE {t_} ADD COLUMN {c_}")
            except sqlite3.OperationalError: pass
        if not d.execute("SELECT 1 FROM packages").fetchone():
            for g_, n, p in [("UID TOPUP", "100 Diamond", 80), ("UID TOPUP", "310 Diamond", 240), ("UID TOPUP", "520 Diamond", 400),
                             ("UID TOPUP", "1060 Diamond", 800), ("Weekly & Monthly", "Weekly Membership", 160),
                             ("Weekly & Monthly", "Monthly Membership", 780), ("Level Up Pass", "Level Up Pass", 70),
                             ("PUBG UC", "60 UC", 90), ("PUBG UC", "325 UC", 450)]:
                d.execute("INSERT INTO packages(game,name,price) VALUES(?,?,?)", (g_, n, p))
        if os.environ.get("ADMIN_PASS"):
            d.execute("INSERT OR IGNORE INTO users(username,pw,is_admin) VALUES(?,?,1)",
                      (os.environ.get("ADMIN_USER", "admin"), generate_password_hash(os.environ["ADMIN_PASS"])))
        d.commit()
init()

today = lambda: time.strftime("%Y-%m-%d")
now = lambda: time.strftime("%Y-%m-%d %H:%M")
def me():
    u = q("SELECT *
