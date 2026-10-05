import os, re, time, random, sqlite3
from flask import Flask, request, jsonify, session, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
DB = os.environ.get("DB_PATH", "data.db")  # Railway: mount a volume at /data, set DB_PATH=/data/data.db
METHODS = ["bKash", "Nagad", "Rocket"]

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
    d = db(); cur = d.execute(sql, a); r = cur.fetchall(); d.commit()
    return (dict(r[0]) if r else None) if one else [dict(x) for x in r]
def run(sql, a=()):
    d = db(); n = d.execute(sql, a).rowcount; d.commit(); return n

def init():
    with app.app_context():
        d = db()
        d.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, pw TEXT,
          balance REAL DEFAULT 0, coins INTEGER DEFAULT 0, last_spin TEXT, is_admin INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS packages(id INTEGER PRIMARY KEY, game TEXT, name TEXT, price REAL);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY, user_id INT, method TEXT, trx TEXT UNIQUE,
          amount REAL, status TEXT DEFAULT 'pending', created TEXT);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INT, package TEXT, player_id TEXT,
          price REAL, status TEXT DEFAULT 'pending', created TEXT);""")
        if not d.execute("SELECT 1 FROM packages").fetchone():
            for g_, n, p in [("Free Fire", "100 Diamond", 80), ("Free Fire", "310 Diamond", 240),
                             ("Free Fire", "520 Diamond", 400), ("Free Fire", "Weekly Membership", 160),
                             ("Free Fire", "Monthly Membership", 780), ("PUBG", "60 UC", 90), ("PUBG", "325 UC", 450)]:
                d.execute("INSERT INTO packages(game,name,price) VALUES(?,?,?)", (g_, n, p))
        ap = os.environ.get("ADMIN_PASS")
        if ap:
            au = os.environ.get("ADMIN_USER", "admin")
            d.execute("INSERT OR IGNORE INTO users(username,pw,is_admin) VALUES(?,?,1)", (au, generate_password_hash(ap)))
        d.commit()
init()

def me():
    u = q("SELECT * FROM users WHERE id=?", (session.get("uid"),), one=True) if session.get("uid") else None
    if not u: raise E("Login korun", 401)
    return u
def admin():
    u = me()
    if not u["is_admin"]: raise E("Forbidden", 403)
    return u
def pub(u): return {k: u[k] for k in ("username", "balance", "coins", "is_admin")}
now = lambda: time.strftime("%Y-%m-%d %H:%M")

@app.get("/")
def index(): return send_from_directory("static", "index.html")
@app.get("/api/config")
def config(): return jsonify(pay_number=os.environ.get("PAY_NUMBER", "01XXXXXXXXX"), methods=METHODS,
                             site=os.environ.get("SITE_NAME", "MY TOPUP"))

@app.post("/api/signup")
def signup():
    j = request.get_json(force=True); u, p = (j.get("username") or "").strip().lower(), j.get("password") or ""
    if not re.fullmatch(r"[a-z0-9_]{3,20}", u): raise E("Username 3-20 ta letter/number hote hobe")
    if len(p) < 6: raise E("Password minimum 6 character")
    try: run("INSERT INTO users(username,pw) VALUES(?,?)", (u, generate_password_hash(p)))
    except sqlite3.IntegrityError: raise E("Username already ache")
    session["uid"] = q("SELECT id FROM users WHERE username=?", (u,), one=True)["id"]
    return jsonify(pub(me()))
@app.post("/api/login")
def login():
    j = request.get_json(force=True)
    u = q("SELECT * FROM users WHERE username=?", ((j.get("username") or "").strip().lower(),), one=True)
    if not u or not check_password_hash(u["pw"], j.get("password") or ""): raise E("Username/password vul", 401)
    session["uid"] = u["id"]; return jsonify(pub(u))
@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=1)
@app.get("/api/me")
def _me(): return jsonify(pub(me()))
@app.get("/api/packages")
def packages(): return jsonify(q("SELECT * FROM packages ORDER BY game, price"))

@app.post("/api/deposit")
def deposit():
    u = me(); j = request.get_json(force=True)
    try: amt = float(j.get("amount"))
    except (TypeError, ValueError): raise E("Amount vul")
    trx = (j.get("trx") or "").strip().upper()
    if amt < 10 or j.get("method") not in METHODS or not 6 <= len(trx) <= 20: raise E("Sob info thik moto din")
    try: run("INSERT INTO deposits(user_id,method,trx,amount,created) VALUES(?,?,?,?,?)", (u["id"], j["method"], trx, amt, now()))
    except sqlite3.IntegrityError: raise E("Ei TrxID age use hoyeche")
    return jsonify(ok=1)

@app.post("/api/order")
def order():
    u = me(); j = request.get_json(force=True)
    p = q("SELECT * FROM packages WHERE id=?", (j.get("package_id"),), one=True)
    pid = (j.get("player_id") or "").strip()
    if not p or not re.fullmatch(r"\d{5,15}", pid): raise E("Package/Player ID vul")
    if not run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (p["price"], u["id"], p["price"])):
        raise E("Balance kom. Add Money korun")
    run("INSERT INTO orders(user_id,package,player_id,price,created) VALUES(?,?,?,?,?)",
        (u["id"], p["game"] + " - " + p["name"], pid, p["price"], now()))
    return jsonify(ok=1)
@app.get("/api/orders")
def orders():
    u = me()
    return jsonify(orders=q("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 30", (u["id"],)),
                   deposits=q("SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 30", (u["id"],)))

@app.post("/api/spin")
def spin():
    u = me(); today = time.strftime("%Y-%m-%d"); c = random.choice([5, 7, 10, 12, 15, 25])
    if not run("UPDATE users SET coins=coins+?, last_spin=? WHERE id=? AND (last_spin IS NULL OR last_spin!=?)",
               (c, today, u["id"], today)): raise E("Ajker spin sesh. Kal abar ashun")
    return jsonify(won=c)
@app.post("/api/redeem")  # 1 coin = 0.1 BDT, min 100 coins
def redeem():
    u = me()
    if not run("UPDATE users SET balance=balance+coins*0.1, coins=0 WHERE id=? AND coins>=100", (u["id"],)):
        raise E("Minimum 100 coin lagbe")
    return jsonify(ok=1)

@app.get("/api/admin/list")
def a_list():
    admin()
    return jsonify(
        deposits=q("SELECT d.*,u.username FROM deposits d JOIN users u ON u.id=d.user_id WHERE d.status='pending' ORDER BY d.id"),
        orders=q("SELECT o.*,u.username FROM orders o JOIN users u ON u.id=o.user_id WHERE o.status='pending' ORDER BY o.id"))
@app.post("/api/admin/deposit/<int:i>/<a>")
def a_dep(i, a):
    admin(); d = q("SELECT * FROM deposits WHERE id=?", (i,), one=True)
    if not d or a not in ("approve", "reject"): raise E("Invalid")
    if run("UPDATE deposits SET status=? WHERE id=? AND status='pending'", ("approved" if a == "approve" else "rejected", i)) and a == "approve":
        run("UPDATE users SET balance=balance+? WHERE id=?", (d["amount"], d["user_id"]))
    return jsonify(ok=1)
@app.post("/api/admin/order/<int:i>/<a>")
def a_ord(i, a):
    admin(); o = q("SELECT * FROM orders WHERE id=?", (i,), one=True)
    if not o or a not in ("done", "cancel"): raise E("Invalid")
    if run("UPDATE orders SET status=? WHERE id=? AND status='pending'", ("done" if a == "done" else "cancelled", i)) and a == "cancel":
        run("UPDATE users SET balance=balance+? WHERE id=?", (o["price"], o["user_id"]))  # refund
    return jsonify(ok=1)
@app.post("/api/admin/package")
def a_pkg():
    admin(); j = request.get_json(force=True)
    run("INSERT INTO packages(game,name,price) VALUES(?,?,?)", (j["game"], j["name"], float(j["price"])))
    return jsonify(ok=1)
