import os, re, time, random, sqlite3, json, hashlib, hmac, secrets, urllib.request, urllib.parse, urllib.error
from flask import Flask, request, jsonify, session, g, send_from_directory, Response, redirect
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=5184000)
DB = os.environ.get("DB_PATH", "data.db")  # Railway: Volume mount /data + DB_PATH=/data/data.db
METHODS = ["bKash", "Nagad", "Rocket", "Binance", "Bybit"]
WHEEL = [5, 7, 10, 12, 15, 25, 8, 20]
DEF = {"site": os.environ.get("SITE_NAME", "TRE TOP UP"), "telegram": "https://t.me/yourchannel",
       "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
       "mail_key": os.environ.get("BREVO_API_KEY", ""), "mail_from": os.environ.get("MAIL_FROM", ""),
       "sms_secret": os.environ.get("SMS_SECRET", ""), "pay_url": os.environ.get("PAY_URL", ""), "pay_key": os.environ.get("PAY_KEY", ""), "mail_url": os.environ.get("MAIL_URL", ""), "mail_secret": os.environ.get("MAIL_SECRET", ""), "auto_topup": "off", "sup_url": os.environ.get("SUPPLIER_URL", ""),
       "sup_key": os.environ.get("SUPPLIER_KEY", ""), "sup_header": "Authorization", "sup_prefix": "Bearer ",
       "sup_body": '{"player_id":"{uid}","product":"{code}","reference":"{order_id}"}', "sup_ok_field": "status", "sup_ok_value": "success",
       "sup_fail_values": "failed,error,rejected,cancelled",
       "uid_url": os.environ.get("UID_URL", ""), "uid_name_field": "nickname", "uid_level_field": "level", "coin_rate": "20", "pending_note": "Apnar order ti processing e ache. Kichukkhon er moddhe complete hobe. Somossha thakle support e jogajog korun.", "notice": "Kono shomossha hole amader Telegram support e jogajog korun", "rules": "⚠️ Order korar age Player ID ar package thik moto check korun.\nVul Player ID te top-up hole company dayi thakbe na.\nOrder complete hote somoy lagte pare, onugroho kore opekkha korun.", "banner_title": "FREE TOURNAMENT", "banner_text": "Match khelun, puroskar jitun!", "banner_img": "", "popup": "🎉 Free Tournament! Ekhoni join korun ar jitun puroskar", "min_withdraw": "50",
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
def give_reward(oid):  # order complete hole coin reward (ekbar)
    o = q("SELECT * FROM orders WHERE id=?", (oid,), one=True)
    if not o or o["status"] != "done" or o["reward"]: return
    r = int(o["price"] * num(S()["coin_rate"]) / 100)
    if r > 0 and run("UPDATE orders SET reward=? WHERE id=? AND reward=0", (r, oid)): run("UPDATE users SET coins=coins+? WHERE id=?", (r, o["user_id"]))
def credit(uid, amt): run("UPDATE users SET balance=balance+? WHERE id=?", (amt, uid))
def S():
    s = dict(DEF); ENVK = ("google_client_id", "sup_url", "sup_key", "mail_key", "mail_from", "mail_url", "mail_secret", "pay_url", "pay_key", "sms_secret", "uid_url")  # khali value hole Railway env variable e fallback korbe
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
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS pay_sms(id INTEGER PRIMARY KEY, trx TEXT UNIQUE, amount REAL, method TEXT, sender TEXT, raw TEXT, used INTEGER DEFAULT 0, created TEXT);
        CREATE TABLE IF NOT EXISTS cats(name TEXT PRIMARY KEY, img TEXT);
        CREATE TABLE IF NOT EXISTS email_codes(email TEXT PRIMARY KEY, username TEXT, pw TEXT, code TEXT, expires INTEGER, tries INTEGER DEFAULT 0, sent INTEGER);""")
        for t_, c_ in [("packages", "code TEXT DEFAULT ''"), ("orders", "note TEXT DEFAULT ''"), ("users", "email TEXT"), ("packages", "section TEXT DEFAULT 'TOPUP'"), ("packages", "stock INTEGER DEFAULT 1"), ("orders", "reward INTEGER DEFAULT 0")]:
            try: d.execute(f"ALTER TABLE {t_} ADD COLUMN {c_}")
            except sqlite3.OperationalError: pass
        if not d.execute("SELECT 1 FROM packages").fetchone():
            for g_, n, p in [("UID TOPUP", "100 Diamond", 80), ("UID TOPUP", "310 Diamond", 240), ("UID TOPUP", "520 Diamond", 400),
                             ("UID TOPUP", "1060 Diamond", 800), ("Weekly & Monthly", "Weekly Membership", 160),
                             ("Weekly & Monthly", "Monthly Membership", 780), ("Level Up Pass", "Level Up Pass", 70),
                             ("PUBG UC", "60 UC", 90), ("PUBG UC", "325 UC", 450)]:
                d.execute("INSERT INTO packages(game,name,price) VALUES(?,?,?)", (g_, n, p))
        d.execute("UPDATE packages SET section='FREE FIRE TOPUP' WHERE section='TOPUP' AND game IN ('UID TOPUP','Weekly & Monthly','Level Up Pass')")
        d.execute("UPDATE packages SET section='OTHERS GAME' WHERE section='TOPUP' AND game='PUBG UC'")
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
def pub(u):
    one = lambda sql: q(sql, (u["id"],), one=True)["s"] or 0
    return dict(username=u["username"], uid=10000 + u["id"], balance=u["balance"], coins=u["coins"], is_admin=u["is_admin"], can_spin=u["last_spin"] != today(),
                added=one("SELECT SUM(amount) s FROM deposits WHERE user_id=? AND status='approved'"),
                spent=one("SELECT SUM(price) s FROM orders WHERE user_id=? AND status!='cancelled'"), orders=one("SELECT COUNT(*) s FROM orders WHERE user_id=?"))
def num(v, d=0):
    try: return float(v)
    except (TypeError, ValueError): return d

@app.get("/")
def index(): return send_from_directory("static", "index.html")
@app.get("/admin")
def admin_page(): return send_from_directory("static", "admin.html")
@app.get("/sw.js")
def sw(): return Response("self.addEventListener('fetch',()=>{});", mimetype="application/javascript")
@app.get("/icon.svg")
def icon(): return Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#6d28d9"/><text x="50" y="66" font-size="52" text-anchor="middle" fill="#fbbf24" font-family="Arial" font-weight="bold">T</text></svg>', mimetype="image/svg+xml")
@app.get("/manifest.json")
def manifest(): return jsonify(name=S()["site"], short_name=S()["site"], start_url="/", display="standalone", background_color="#070b1a",
                                theme_color="#6d28d9", icons=[{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}])
@app.get("/api/config")
def config():
    s = S(); return jsonify(site=s["site"], telegram=s["telegram"], popup=s["popup"], notice=s["notice"], rules=s["rules"], coin_rate=num(s["coin_rate"]), uidcheck=bool(s["uid_url"]), pending_note=s["pending_note"], banner_title=s["banner_title"], banner_text=s["banner_text"], banner_img=s["banner_img"], auto=bool(s["pay_url"] and s["pay_key"]),
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
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
HITS = {}
def limit(key, n, sec):
    t = time.time(); L = [x for x in HITS.get(key, []) if t - x < sec]
    if len(L) >= n: raise E("Onek bar chesta korechen, pore abar korun", 429)
    L.append(t); HITS[key] = L
def hc(code): return hashlib.sha256((code + app.secret_key).encode()).hexdigest()
def send_mail(to, subject, html):  # 1) Google Apps Script relay (MAIL_URL)  2) Brevo API (BREVO_API_KEY). Railway te SMTP block thake
    s = S()
    if s["mail_url"]:
        body = json.dumps({"secret": s["mail_secret"], "to": to, "subject": subject, "html": html, "name": s["site"]}).encode()
        req = urllib.request.Request(s["mail_url"], body, {"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25) as r: ok = json.loads(r.read().decode() or "{}").get("ok")
        except Exception: ok = False
        if not ok: raise E("Email pathano jayni. Pore abar chesta korun", 502)
        return
    if not s["mail_key"] or not s["mail_from"]: raise E("Email service set kora nai (MAIL_URL + MAIL_SECRET)", 500)
    body = json.dumps({"sender": {"name": s["site"], "email": s["mail_from"]}, "to": [{"email": to}], "subject": subject, "htmlContent": html}).encode()
    req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", body,
                                 {"api-key": s["mail_key"], "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r: r.read()
    except Exception: raise E("Email pathano jayni. Pore abar chesta korun", 502)
@app.post("/api/signup/start")
def signup_start():
    j = request.get_json(force=True); u = (j.get("username") or "").strip().lower()
    e = (j.get("email") or "").strip().lower(); p = j.get("password") or ""
    limit("ip:" + (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[-1].strip(), 6, 600)
    if not re.fullmatch(r"[a-z0-9_]{3,20}", u): raise E("Username 3-20 ta letter/number hote hobe")
    if not EMAIL_RE.match(e) or len(e) > 120: raise E("Valid email address din")
    if len(p) < 6: raise E("Password minimum 6 character")
    if q("SELECT 1 FROM users WHERE username=?", (u,), one=True): raise E("Username already ache")
    if q("SELECT 1 FROM users WHERE email=?", (e,), one=True): raise E("Ei email diye account ache. Login korun")
    old = q("SELECT sent FROM email_codes WHERE email=?", (e,), one=True)
    if old and time.time() - old["sent"] < 60: raise E("1 minute por abar code nin")
    code = "%06d" % secrets.randbelow(10 ** 6); site = S()["site"]
    send_mail(e, "%s verification code: %s" % (site, code),
              "<div style='font-family:Arial,sans-serif'><h2>%s</h2><p>Apnar verification code:</p>"
              "<p style='font-size:32px;font-weight:bold;letter-spacing:6px'>%s</p><p>Code ta 10 minute valid thakbe. Apni na chaile ei email ignore korun.</p></div>" % (site, code))
    run("INSERT OR REPLACE INTO email_codes(email,username,pw,code,expires,tries,sent) VALUES(?,?,?,?,?,0,?)",
        (e, u, generate_password_hash(p), hc(code), int(time.time()) + 600, int(time.time())))
    return jsonify(ok=1)
@app.post("/api/signup/verify")
def signup_verify():
    j = request.get_json(force=True); e = (j.get("email") or "").strip().lower(); code = str(j.get("code") or "").strip()
    r = q("SELECT * FROM email_codes WHERE email=?", (e,), one=True)
    if not r or r["expires"] < time.time(): raise E("Code expire hoyeche, abar code nin")
    if r["tries"] >= 5: raise E("Onek bar vul hoyeche, abar code nin")
    if not hmac.compare_digest(r["code"], hc(code)):
        run("UPDATE email_codes SET tries=tries+1 WHERE email=?", (e,)); raise E("Code vul")
    try: run("INSERT INTO users(username,pw,email) VALUES(?,?,?)", (r["username"], r["pw"], e))
    except sqlite3.IntegrityError: raise E("Username ba email age nea hoyeche, abar signup korun")
    run("DELETE FROM email_codes WHERE email=?", (e,))
    u = q("SELECT * FROM users WHERE email=?", (e,), one=True)
    session.permanent = True; session["uid"] = u["id"]; return jsonify(pub(u))
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
@app.get("/api/latest")
def latest():
    r = q("SELECT o.package,o.created,u.username FROM orders o JOIN users u ON u.id=o.user_id WHERE o.status='done' ORDER BY o.id DESC LIMIT 8")
    for x in r: x["username"] = x["username"][:3] + "***"
    return jsonify(r)
@app.get("/api/packages")
def packages(): return jsonify(q("SELECT id,game,name,price,section,stock FROM packages ORDER BY id"))
@app.get("/api/cats")
def cats(): return jsonify({r["name"]: r["img"] for r in q("SELECT * FROM cats")})
@app.post("/api/admin/cat")
def a_cat():
    admin(); j = request.get_json(force=True); n = (j.get("name") or "").strip()
    if not n: raise E("Category naam din")
    run("INSERT INTO cats(name,img) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET img=excluded.img", (n, (j.get("img") or "").strip())); return jsonify(ok=1)
@app.post("/api/admin/package/<int:i>/update")
def a_pupd(i):
    admin(); j = request.get_json(force=True); p = q("SELECT * FROM packages WHERE id=?", (i,), one=True)
    if not p: raise E("Package nai", 404)
    g_ = lambda k: j[k] if k in j else p[k]
    run("UPDATE packages SET game=?,name=?,price=?,section=?,code=?,stock=? WHERE id=?",
        (str(g_("game")).strip(), str(g_("name")).strip(), num(g_("price")), str(g_("section")).strip().upper(), str(g_("code") or "").strip(), 1 if g_("stock") else 0, i)); return jsonify(ok=1)


def gw(path, body):
    s = S()
    if not s["pay_url"] or not s["pay_key"]: raise E("Auto payment ekhono chalu nai", 500)
    base = s["pay_url"].strip().rstrip("/").split("/api/")[0]
    req = urllib.request.Request(base + path, json.dumps(body).encode(), {"RT-UDDOKTAPAY-API-KEY": s["pay_key"], "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read().decode() or "{}")
    except Exception: raise E("Payment gateway e connect hoy nai, pore abar chesta korun", 502)
def dsig(uid): return hmac.new(app.secret_key.encode(), ("dep:%s" % uid).encode(), hashlib.sha256).hexdigest()[:24]
def settle(inv):  # gateway theke verify kore balance add kore (ekbar-i)
    r = gw("/api/verify-payment", {"invoice_id": inv})
    if str(r.get("status", "")).upper() != "COMPLETED": raise E("Payment complete hoyni")
    md = r.get("metadata") or {}; amt = num(r.get("amount"))
    try: uid = int(md.get("uid") or 0)
    except (TypeError, ValueError): uid = 0
    if not uid or amt <= 0 or not hmac.compare_digest(str(md.get("sig") or ""), dsig(uid)): raise E("Payment info vul")
    try: run("INSERT INTO deposits(user_id,method,trx,amount,status,created) VALUES(?,?,?,?,'approved',?)", (uid, str(r.get("payment_method") or "auto")[:20], "UP-" + str(inv)[:60], amt, now()))
    except sqlite3.IntegrityError: return False
    credit(uid, amt); return True
def clientip(): return (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[-1].strip()
@app.post("/api/deposit/auto")
def deposit_auto():
    u = me(); amt = num((request.get_json(force=True) or {}).get("amount"))
    if amt < 10 or amt > 50000: raise E("Minimum 10 ar maximum 50000 taka")
    base = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0] + "://" + request.host
    r = gw("/api/checkout-v2", {"full_name": u["username"], "email": u["email"] or "customer@example.com", "amount": str(amt),
        "metadata": {"uid": u["id"], "sig": dsig(u["id"])}, "redirect_url": base + "/api/deposit/return", "return_type": "GET",
        "cancel_url": base + "/?dep=cancel", "webhook_url": base + "/api/deposit/webhook"})
    if not r.get("payment_url"): raise E("Payment link toiri hoy nai", 502)
    return jsonify(url=r["payment_url"])
@app.get("/api/deposit/return")
def deposit_return():
    limit("ret:" + clientip(), 30, 600)
    try: settle(request.args.get("invoice_id", "")); return redirect("/?dep=ok")
    except E: return redirect("/?dep=fail")
@app.post("/api/deposit/webhook")
def deposit_webhook():
    try: settle((request.get_json(silent=True) or {}).get("invoice_id", ""))
    except E: pass
    return "ok"
SMS_FROM = re.compile(r"bkash|nagad|rocket|16216|dbbl|upay", re.I)
def parse_sms(txt):
    t = " ".join(str(txt).split())
    if not re.search(r"receiv", t, re.I): return None
    num_ = r"([\d,]+(?:\.\d+)?)"
    a = (re.search(r"receiv\w*[^\d]{0,15}" + num_, t, re.I) or re.search(r"Amount\s*[:\-]?\s*(?:Tk\.?|BDT|৳)?\s*" + num_, t, re.I)
         or re.search(r"(?:Tk\.?|BDT|৳)\s*" + num_ + r"\s*receiv", t, re.I))
    x = re.search(r"(?:Trx\s*ID|Txn\s*ID|Transaction\s*ID|Trans\s*ID)\s*[:\-]?\s*([A-Za-z0-9]{6,20})", t, re.I)
    if not a or not x: return None
    f = re.search(r"(?:from|Sender)\s*:?\s*(?:A/C:?\s*)?(01\d{9})", t, re.I)
    m = "bKash" if re.search(r"bkash", t, re.I) else "Nagad" if re.search(r"nagad", t, re.I) else "Rocket" if re.search(r"rocket|dbbl", t, re.I) else ""
    return dict(amount=float(a.group(1).replace(",", "")), trx=x.group(1).upper(), method=m, sender=f.group(1) if f else "")
def auto_match(trx):  # SMS + pending deposit mille gele auto approve
    sm = q("SELECT * FROM pay_sms WHERE trx=? AND used=0", (trx,), one=True)
    d = q("SELECT * FROM deposits WHERE trx=? AND status='pending'", (trx,), one=True)
    if not sm or not d or abs(d["amount"] - sm["amount"]) > 0.5: return False
    if not run("UPDATE pay_sms SET used=1 WHERE id=? AND used=0", (sm["id"],)): return False
    if not run("UPDATE deposits SET status='approved' WHERE id=? AND status='pending'", (d["id"],)): return False
    credit(d["user_id"], sm["amount"]); return True
@app.route("/api/sms/hook", methods=["GET", "POST"])
def sms_hook():
    sec = S()["sms_secret"]; j = request.get_json(silent=True) or {}
    pick = lambda *ks: next((str(v) for k in ks for v in [j.get(k) or request.form.get(k) or request.args.get(k)] if v), "")
    got = pick("secret") or request.headers.get("X-Secret", "")
    if not sec or not hmac.compare_digest(got, sec): return "forbidden", 403
    limit("sms", 120, 60)
    msg = pick("message", "content", "text", "body", "sms"); frm = pick("from", "sender", "number", "address")
    if not msg: return "empty", 400
    r = None if (frm and not SMS_FROM.search(frm)) else parse_sms(msg)
    if r:
        run("INSERT OR IGNORE INTO pay_sms(trx,amount,method,sender,raw,created) VALUES(?,?,?,?,?,?)", (r["trx"], r["amount"], r["method"], r["sender"], msg[:400], now()))
        auto_match(r["trx"])
    else: run("INSERT INTO pay_sms(trx,amount,method,sender,raw,used,created) VALUES(NULL,0,'',?,?,2,?)", (frm[:40], msg[:400], now()))
    return "ok"
@app.post("/api/deposit")
def deposit():
    u = me(); j = request.get_json(force=True); amt = num(j.get("amount")); trx = (j.get("trx") or "").strip().upper()
    if amt < 10 or j.get("method") not in METHODS or not 6 <= len(trx) <= 64: raise E("Sob info thik moto din")
    try: run("INSERT INTO deposits(user_id,method,trx,amount,created) VALUES(?,?,?,?,?)", (u["id"], j["method"], trx, amt, now()))
    except sqlite3.IntegrityError:
        d = q("SELECT * FROM deposits WHERE trx=?", (trx,), one=True)
        if not (d and d["user_id"] == u["id"] and d["status"] == "pending"): raise E("Ei TrxID age use hoyeche")
    return jsonify(ok=1, status="approved" if auto_match(trx) else "pending")
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
PCACHE = {}
@app.get("/api/player/<uid>")
def player(uid):  # Player ID er name/level (admin e set kora lookup API theke)
    u = me()
    if not re.fullmatch(r"\d{5,15}", uid): raise E("Sothik Player ID din")
    s = S()
    if not s["uid_url"]: return jsonify(configured=False)
    limit("pc:%s" % u["id"], 20, 60)
    hit = PCACHE.get(uid)
    if hit and time.time() - hit[0] < 600: return jsonify(hit[1])
    try:
        req = urllib.request.Request(s["uid_url"].replace("{uid}", uid), headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as r: j = json.loads(r.read(200000).decode())
    except Exception: raise E("Player info ante parini, pore abar chesta korun", 502)
    name = dig(j, s["uid_name_field"] or "nickname"); lv = dig(j, s["uid_level_field"] or "level")
    out = dict(configured=True, found=bool(name), name=str(name or "")[:40], level=lv if isinstance(lv, (int, float, str)) else None)
    if out["found"]:
        if len(PCACHE) > 2000: PCACHE.clear()
        PCACHE[uid] = (time.time(), out)
    return jsonify(out)
@app.post("/api/order")
def order():
    u = me(); j = request.get_json(force=True)
    p = q("SELECT * FROM packages WHERE id=?", (j.get("package_id"),), one=True); pid = (j.get("player_id") or "").strip()
    if not p or not re.fullmatch(r"\d{5,15}", pid): raise E("Package/Player ID vul")
    if p["stock"] == 0: raise E("Ei package ekhon stock e nai")
    if not run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (p["price"], u["id"], p["price"])): raise E("Balance kom. Add Money korun")
    d = db(); oid = d.execute("INSERT INTO orders(user_id,package,player_id,price,created) VALUES(?,?,?,?,?)",
                              (u["id"], p["game"] + " - " + p["name"], pid, p["price"], now())).lastrowid; d.commit()
    res = fulfill(oid, p.get("code") or "", pid)
    if res:
        run("UPDATE orders SET status=?, note=? WHERE id=?", (res[0], res[1], oid))
        if res[0] == "cancelled": credit(u["id"], p["price"])
        if res[0] == "done": give_reward(oid)
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
AD = {"sms": "SELECT * FROM pay_sms ORDER BY id DESC LIMIT 60", "deposits": "SELECT d.*,u.username FROM deposits d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT 60",
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
        deposited=c("SELECT SUM(amount) c FROM deposits WHERE status='approved'"),
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
    if (k, a) == ("order", "done"): give_reward(i)
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
    run("INSERT INTO packages(game,name,price,code,section) VALUES(?,?,?,?,?)", (j.get("game") or "UID TOPUP", j.get("name") or "Package", num(j.get("price")), (j.get("code") or "").strip(), (j.get("section") or "TOPUP").strip().upper())); return jsonify(ok=1)
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
