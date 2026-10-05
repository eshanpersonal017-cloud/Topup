import os, re, time, random, sqlite3, json, urllib.request, urllib.parse, urllib.error
from flask import Flask, request, jsonify, session, g, send_from_directory, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=5184000)
DB = os.environ.get("DB_PATH", "data.db")  # Railway: Volume mount /data + DB_PATH=/data/data.db
METHODS = ["bKash", "Nagad", "Rocket", "Binance", "Bybit"]
WHEEL = [5, 7, 10, 12, 15, 25, 8, 20]
DEF = {"site": os.environ.get("SITE_NAME", "MY TOPUP"), "telegram": "https://t.me/yourchannel",
       "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""), "auto_topup": "off", "sup_url": os.environ.get("SUPPLIER_URL", ""),
       "sup_key": os.environ.get("SUPPLIER_KEY", ""), "sup_header": "Authorization", "sup_prefix": "Bearer ",
       "sup_body": '{"player_id":"{uid}","product":"{code}","reference":"{order_id}"}', "sup_ok_field": "status", "sup_ok_value": "success",
       "sup_fail_values": "failed,error,rejected,cancelled",
       "popup": "🎉 Free Tournament! Ekhoni join korun ar jitun puroskar", "min_withdraw": "50",
       **{"pay_" + m: os.environ.get("PAY_NUMBER", "01XXXXXXXXX") for m in METHODS}}

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
    s = dict(DEF); ENVK = ("google_client_id", "sup_url", "sup_key")  # khali value hole Railway env variable e fallback korbe
    s.update({r["k"]: r["v"] for r in q("SELECT * FROM settings") if r["v"].strip() or r["k"] not in ENVK}); return s

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
    u = q("SELECT * FROM users WHERE id=?", (session.get("uid"),), one=True) if session.get("uid") else None
    if not u: raise E("Login korun", 401)
    if u["banned"]: raise E("Account banned", 403)
    return u
def admin():
    u = me()
    if not u["is_admin"]: raise E("Forbidden", 403)
def pub(u): return dict(username=u["username"], uid=10000 + u["id"], balance=u["balance"], coins=u["coins"],
                        is_admin=u["is_admin"], can_spin=u["last_spin"] != today())
def num(v, d=0):
    try: return float(v)
    except (TypeError, ValueError): return d

@app.get("/")
def index(): return send_from_directory("static", "index.html")
@app.get("/admin")
def admin_page(): return send_from_directory("static", "index.html")
@app.get("/sw.js")
def sw(): return Response("self.addEventListener('fetch',()=>{});", mimetype="application/javascript")
@app.get("/icon.svg")
def icon(): return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#6d28d9"/><text x="50" y="66" font-size="52" text-anchor="middle" fill="#fbbf24" font-family="Arial" font-weight="bold">T</text></svg>', mimetype="image/svg+xml")
@app.get("/manifest.json")
def manifest(): return jsonify(name=S()["site"], short_name=S()["site"], start_url="/", display="standalone", background_color="#070b1a",
                                theme_color="#6d28d9", icons=[{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}])
@app.get("/api/config")
def config():
    s = S(); return jsonify(site=s["site"], telegram=s["telegram"], popup=s["popup"], min_withdraw=s["min_withdraw"],
                            methods=[{"m": m, "n": s["pay_" + m]} for m in METHODS], wheel=WHEEL, google=s["google_client_id"])

@app.post("/api/google")
def google():
    cid = S()["google_client_id"]
    if not cid: raise E("Google login set kora nai")
    try:
        tok = urllib.parse.quote(request.get_json(force=True).get("credential") or "")
        with urllib.request.urlopen("https://oauth2.googleapis.com/tokeninfo?id_token=" + tok, timeout=10) as r: j = json.loads(r.read())
    except Exception: raise E("Google verify hoy nai", 401)
    if j.get("aud") != cid or str(j.get("email_verified")).lower() != "true": raise E("Google verify hoy nai", 401)
    email = j["email"].lower(); u = q("SELECT * FROM users WHERE email=?", (email,), one=True)
    if not u:
        base = re.sub(r"[^a-z0-9_]", "", email.split("@")[0])[:14] or "user"; name = base
        while q("SELECT 1 FROM users WHERE username=?", (name,), one=True): name = base + str(random.randint(100, 9999))
        run("INSERT INTO users(username,pw,email) VALUES(?,?,?)", (name, generate_password_hash(os.urandom(16).hex()), email))
        u = q("SELECT * FROM users WHERE email=?", (email,), one=True)
    if u["banned"]: raise E("Account banned", 403)
    session.permanent = True; session["uid"] = u["id"]; return jsonify(pub(u))
@app.post("/api/signup")
def signup():
    j = request.get_json(force=True); u, p = (j.get("username") or "").strip().lower(), j.get("password") or ""
    if not re.fullmatch(r"[a-z0-9_]{3,20}", u): raise E("Username 3-20 ta letter/number hote hobe")
    if len(p) < 6: raise E("Password minimum 6 character")
    try: run("INSERT INTO users(username,pw) VALUES(?,?)", (u, generate_password_hash(p)))
    except sqlite3.IntegrityError: raise E("Username already ache")
    session.permanent = True; session["uid"] = q("SELECT id FROM users WHERE username=?", (u,), one=True)["id"]
    return jsonify(pub(me()))
@app.post("/api/login")
def login():
    j = request.get_json(force=True)
    u = q("SELECT * FROM users WHERE username=?", ((j.get("username") or "").strip().lower(),), one=True)
    if not u or not check_password_hash(u["pw"], j.get("password") or ""): raise E("Username/password vul", 401)
    session.permanent = True; session["uid"] = u["id"]; return jsonify(pub(u))
@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=1)
@app.get("/api/me")
def _me(): return jsonify(pub(me()))
@app.get("/api/packages")
def packages(): return jsonify(q("SELECT * FROM packages ORDER BY id"))

@app.post("/api/deposit")
def deposit():
    u = me(); j = request.get_json(force=True); amt = num(j.get("amount")); trx = (j.get("trx") or "").strip().upper()
    if amt < 10 or j.get("method") not in METHODS or not 6 <= len(trx) <= 64: raise E("Sob info thik moto din")
    try: run("INSERT INTO deposits(user_id,method,trx,amount,created) VALUES(?,?,?,?,?)", (u["id"], j["method"], trx, amt, now()))
    except sqlite3.IntegrityError: raise E("Ei TrxID age use hoyeche")
    return jsonify(ok=1)
@app.post("/api/withdraw")
def withdraw():
    u = me(); j = request.get_json(force=True); amt = num(j.get("amount")); acc = (j.get("account") or "").strip()[:80]
    if j.get("method") not in METHODS or not acc or amt < num(S()["min_withdraw"], 50): raise E("Minimum " + S()["min_withdraw"] + " taka, number/address din")
    if not run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (amt, u["id"], amt)): raise E("Balance kom")
    run("INSERT INTO withdrawals(user_id,method,account,amount,created) VALUES(?,?,?,?,?)", (u["id"], j["method"], acc, amt, now()))
    return jsonify(ok=1)
def dig(o, path):
    for k in path.split("."): o = o.get(k) if isinstance(o, dict) else None
    return o
def fulfill(oid, code, pid):  # supplier API call. None = manual order
    s = S()
    if s["auto_topup"] != "on" or not s["sup_url"] or not code: return None
    body = s["sup_body"].replace("{uid}", pid).replace("{code}", code).replace("{order_id}", str(oid))
    h = {"Content-Type": "application/json"}
    if s["sup_key"]: h[s["sup_header"] or "Authorization"] = (s["sup_prefix"] or "") + s["sup_key"]
    try:
        with urllib.request.urlopen(urllib.request.Request(s["sup_url"], body.encode(), h, method="POST"), timeout=25) as r: txt = r.read().decode()[:400]
    except urllib.error.HTTPError as e: return ("pending", "Supplier HTTP %s" % e.code)
    except Exception as e: return ("pending", "Supplier error: " + str(e)[:80])  # unknown result: admin check korbe, auto refund hobe na
    try: v = str(dig(json.loads(txt), s["sup_ok_field"])).lower()
    except ValueError: v = ""
    if v == s["sup_ok_value"].lower(): return ("done", "Auto: " + txt[:150])
    if v in [x.strip().lower() for x in s["sup_fail_values"].split(",")]: return ("cancelled", "Auto failed: " + txt[:150])
    return ("pending", "Supplier: " + txt[:150])
@app.post("/api/order")
def order():
    u = me(); j = request.get_json(force=True)
    p = q("SELECT * FROM packages WHERE id=?", (j.get("package_id"),), one=True); pid = (j.get("player_id") or "").strip()
    if not p or not re.fullmatch(r"\d{5,15}", pid): raise E("Package/Player ID vul")
    if not run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (p["price"], u["id"], p["price"])): raise E("Balance kom. Add Money korun")
    d = db(); oid = d.execute("INSERT INTO orders(user_id,package,player_id,price,created) VALUES(?,?,?,?,?)",
                              (u["id"], p["game"] + " - " + p["name"], pid, p["price"], now())).lastrowid; d.commit()
    res = fulfill(oid, p.get("code") or "", pid)
    if res:
        run("UPDATE orders SET status=?, note=? WHERE id=?", (res[0], res[1], oid))
        if res[0] == "cancelled": credit(u["id"], p["price"])
    return jsonify(ok=1, status=res[0] if res else "pending")
@app.get("/api/history")
def history():
    i = me()["id"]; f = lambda t: q(f"SELECT * FROM {t} WHERE user_id=? ORDER BY id DESC LIMIT 25", (i,))
    return jsonify(orders=f("orders"), deposits=f("deposits"), withdrawals=f("withdrawals"))

@app.get("/api/tournaments")
def t_list():
    u = me()
    rows = q("""SELECT t.*,(SELECT COUNT(*) FROM joins j WHERE j.tid=t.id) joined,
      (SELECT COUNT(*) FROM joins j WHERE j.tid=t.id AND j.user_id=?) mine FROM tournaments t ORDER BY t.id DESC LIMIT 40""", (u["id"],))
    for r in rows:
        if not r["mine"]: r["room_id"] = r["room_pass"] = ""
    return jsonify(rows)
@app.post("/api/tournament/<int:i>/join")
def t_join(i):
    u = me(); t = q("SELECT * FROM tournaments WHERE id=?", (i,), one=True); ign = (request.get_json(force=True).get("ign") or "").strip()[:30]
    if not t or t["status"] != "open" or not ign: raise E("Match join kora jabe na (in-game name din)")
    if q("SELECT 1 FROM joins WHERE tid=? AND user_id=?", (i, u["id"]), one=True): raise E("Already join korechen")
    if q("SELECT COUNT(*) c FROM joins WHERE tid=?", (i,), one=True)["c"] >= t["slots"]: raise E("Slot full")
    if not run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (t["entry"], u["id"], t["entry"])): raise E("Balance kom. Add Money korun")
    try: run("INSERT INTO joins(tid,user_id,ign) VALUES(?,?,?)", (i, u["id"], ign))
    except sqlite3.IntegrityError: credit(u["id"], t["entry"]); raise E("Already join korechen")
    return jsonify(ok=1)

@app.post("/api/spin")
def spin():
    u = me(); idx = random.randrange(len(WHEEL)); c = WHEEL[idx]
    if not run("UPDATE users SET coins=coins+?, last_spin=? WHERE id=? AND (last_spin IS NULL OR last_spin!=?)", (c, today(), u["id"], today())):
        raise E("Ajker spin sesh. Kal abar ashun")
    run("INSERT INTO spins(user_id,coins,created) VALUES(?,?,?)", (u["id"], c, now()))
    return jsonify(won=c, idx=idx)
@app.get("/api/spins")
def spins():
    me(); r = q("SELECT s.coins,s.created,u.username FROM spins s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 12")
    for x in r: x["username"] = x["username"][:2] + "***"
    return jsonify(r)
@app.post("/api/redeem")  # 1 coin = 0.1 BDT, min 100
def redeem():
    u = me()
    if not run("UPDATE users SET balance=balance+coins*0.1, coins=0 WHERE id=? AND coins>=100", (u["id"],)): raise E("Minimum 100 coin lagbe")
    return jsonify(ok=1)

# ---------------- ADMIN ----------------
AD = {"deposits": "SELECT d.*,u.username FROM deposits d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT 60",
      "orders": "SELECT d.*,u.username FROM orders d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT 60",
      "withdrawals": "SELECT d.*,u.username FROM withdrawals d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT 60",
      "tournaments": "SELECT t.*,(SELECT COUNT(*) FROM joins j WHERE j.tid=t.id) joined FROM tournaments t ORDER BY id DESC LIMIT 40",
      "packages": "SELECT * FROM packages ORDER BY id",
      "users": "SELECT id,username,balance,coins,banned,is_admin FROM users ORDER BY id DESC LIMIT 100"}
@app.get("/api/admin/data/<t>")
def a_data(t):
    admin()
    if t == "settings": return jsonify(S())
    if t not in AD: raise E("Invalid")
    return jsonify(q(AD[t]))
@app.get("/api/admin/stats")
def a_stats():
    admin(); c = lambda s: q(s, one=True)["c"] or 0
    return jsonify(users=c("SELECT COUNT(*) c FROM users"), balances=c("SELECT SUM(balance) c FROM users"),
        pending_deposits=c("SELECT COUNT(*) c FROM deposits WHERE status='pending'"), pending_orders=c("SELECT COUNT(*) c FROM orders WHERE status='pending'"),
        pending_withdraws=c("SELECT COUNT(*) c FROM withdrawals WHERE status='pending'"), deposited=c("SELECT SUM(amount) c FROM deposits WHERE status='approved'"),
        sales=c("SELECT SUM(price) c FROM orders WHERE status='done'"), open_matches=c("SELECT COUNT(*) c FROM tournaments WHERE status='open'"))
T = {"deposit": ("deposits", {"approve": "approved", "reject": "rejected"}), "order": ("orders", {"done": "done", "cancel": "cancelled"}),
     "withdraw": ("withdrawals", {"approve": "paid", "reject": "rejected"})}
@app.post("/api/admin/act/<k>/<int:i>/<a>")
def a_act(k, i, a):
    admin()
    if k not in T or a not in T[k][1]: raise E("Invalid")
    tb, m = T[k]; r = q(f"SELECT * FROM {tb} WHERE id=?", (i,), one=True)
    if not r or not run(f"UPDATE {tb} SET status=? WHERE id=? AND status='pending'", (m[a], i)): raise E("Already processed")
    if (k, a) == ("deposit", "approve"): credit(r["user_id"], r["amount"])
    if (k, a) == ("order", "cancel"): credit(r["user_id"], r["price"])
    if (k, a) == ("withdraw", "reject"): credit(r["user_id"], r["amount"])
    return jsonify(ok=1)
@app.post("/api/admin/tournament")
def a_tadd():
    admin(); j = request.get_json(force=True)
    run("INSERT INTO tournaments(title,mode,prize,entry,per_kill,min_level,slots,start) VALUES(?,?,?,?,?,?,?,?)",
        (j.get("title") or "Match", j.get("mode") or "SOLO", num(j.get("prize")), num(j.get("entry")), num(j.get("per_kill")),
         int(num(j.get("min_level"))), int(num(j.get("slots"), 48)), j.get("start") or ""))
    return jsonify(ok=1)
@app.post("/api/admin/tournament/<int:i>/room")
def a_room(i):
    admin(); j = request.get_json(force=True)
    run("UPDATE tournaments SET room_id=?, room_pass=? WHERE id=?", (j.get("room_id", ""), j.get("room_pass", ""), i)); return jsonify(ok=1)
@app.post("/api/admin/tournament/<int:i>/finish")
def a_finish(i):  # winners: "user1:500,user2:200"
    admin(); w = (request.get_json(force=True).get("winners") or "").strip()
    if not run("UPDATE tournaments SET status='done' WHERE id=? AND status='open'", (i,)): raise E("Already finished")
    for part in filter(None, w.split(",")):
        n, _, a = part.partition(":"); u = q("SELECT id FROM users WHERE username=?", (n.strip().lower(),), one=True)
        if u and num(a) > 0: credit(u["id"], num(a))
    return jsonify(ok=1)
@app.post("/api/admin/package")
def a_pkg():
    admin(); j = request.get_json(force=True)
    run("INSERT INTO packages(game,name,price,code) VALUES(?,?,?,?)", (j.get("game") or "UID TOPUP", j.get("name") or "Package", num(j.get("price")), (j.get("code") or "").strip())); return jsonify(ok=1)
@app.post("/api/admin/package/<int:i>/code")
def a_pcode(i): admin(); run("UPDATE packages SET code=? WHERE id=?", ((request.get_json(force=True).get("code") or "").strip(), i)); return jsonify(ok=1)
@app.post("/api/admin/package/<int:i>/delete")
def a_pdel(i): admin(); run("DELETE FROM packages WHERE id=?", (i,)); return jsonify(ok=1)
@app.post("/api/admin/user/<int:i>/<a>")
def a_user(i, a):
    admin(); j = request.get_json(force=True)
    if a == "balance": credit(i, num(j.get("delta")))
    elif a in ("ban", "unban"): run("UPDATE users SET banned=? WHERE id=? AND is_admin=0", (int(a == "ban"), i))
    else: raise E("Invalid")
    return jsonify(ok=1)
@app.post("/api/admin/settings")
def a_set():
    admin(); j = request.get_json(force=True)
    for k in DEF:
        if k in j: run("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(j[k])))
    return jsonify(ok=1)
