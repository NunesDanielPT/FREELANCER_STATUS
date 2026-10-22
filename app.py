#!/usr/bin/env python3
"""Claquete - organizador de eventos e faturas para freelancers (so biblioteca standard)."""
import json, os, re, ssl, time, math, hmac, html, hashlib, secrets, sqlite3, smtplib, calendar, threading, struct, zlib
from functools import lru_cache
import datetime as dt
from email.message import EmailMessage
from email.utils import formataddr
from http import cookies
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import i18n
from i18n import tx, M0, M1

DB = os.environ.get("DB_PATH", "/data/claquete.db")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
INVITE = os.environ.get("INVITE_CODE", "")
MES = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split()

e = lambda s: M0 + html.escape("" if s is None else str(s)) + M1      # texto de utilizadores: nunca é traduzido
eh = lambda s: html.escape("" if s is None else str(s))              # texto fixo do código: é traduzido
now_str = lambda: dt.datetime.now().strftime("%Y-%m-%d %H:%M")
def dsep(): return "." if i18n.lang() == "en" else ","
today = lambda: dt.date.today()
D = dt.date.fromisoformat

def eur(v):
    s, l = f"{(v or 0):,.2f}", i18n.lang()
    if l == "en": return "€" + s
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", {"pt": " ", "es": ".", "it": ".", "fr": "\u202f"}[l]) + " €"
def short(v):
    s = f"{v / 1000:g}k" if v >= 1000 else f"{v:g}"
    return s.replace(".", ",") if v >= 1000 and i18n.lang() != "en" else s
def num(s):
    s = str(s).replace(" ", "").replace("\u202f", "")
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else: s = s.replace(",", ".")
    try: return float(s)
    except ValueError: return 0.0
def okdate(s):
    try: return D(s).isoformat()
    except Exception: return None
def ds(s): d = D(s); return f"{d.day} {MES[d.month - 1][:3]}"
def drange(a, b):
    A, B = D(a), D(b)
    if a == b: return f"{ds(a)} {B.year}"
    return f"{ds(a)}{' ' + str(A.year) if A.year != B.year else ''} – {ds(b)} {B.year}"
def ndays(a, b): return (D(b) - D(a)).days + 1
def ini(n): return "".join(w[0] for w in (n or "?").split()[:2]).upper()
def month_nav(m):
    try: f = dt.datetime.strptime(m, "%Y-%m").date()
    except ValueError: f = today().replace(day=1)
    return f, (f - dt.timedelta(1)).strftime("%Y-%m"), (f + dt.timedelta(32)).replace(day=1).strftime("%Y-%m")

# ---------------------------------------------------------------- base de dados
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("pragma foreign_keys=on"); return c
def rows(q, a=()):
    c = db()
    try: return c.execute(q, a).fetchall()
    finally: c.close()
def one(q, a=()):
    r = rows(q, a); return r[0] if r else None
def run(q, a=()):
    c = db()
    try:
        cur = c.execute(q, a); c.commit(); return cur.lastrowid
    finally: c.close()

BACKUP_DIR = os.path.join(os.path.dirname(DB), "backups")
BK_RE = r"^claquete-\d{8}-\d{6}-[a-z]+\.db$"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
COLOR_KEYS = ("c_brand", "c_todo", "c_inv", "c_paid")
DEFAULTS = {
    "site_name": "Claquete",
    "hero_title": "Sabe sempre o que falta faturar e o que falta receber.",
    "hero_text": "Eventos, clientes e faturas num só sítio, feito para freelancers de audiovisual. Não emite faturas: só te ajuda a não perder nenhuma.",
    "c_brand": "#3b4cdb", "c_todo": "#e5484d", "c_inv": "#f0a020", "c_paid": "#2fa56b",
    "reg_open": "1", "invite": "", "lang": "pt",
    "ad_on": "0", "ad_img": "", "ad_link": "", "ad_text": "", "ad_app": "1", "ad_auth": "0",
}

# ---------------------------------------------------------------- configuração do site (editável no Admin)
def cfg():
    d = dict(DEFAULTS)
    for r in rows("select k, v from kv where k like 'cfg.%'"): d[r["k"][4:]] = r["v"]
    for k in COLOR_KEYS:
        if not HEX.match(d[k] or ""): d[k] = DEFAULTS[k]
    return d

def set_cfg(d):
    c = db()
    try:
        for k, v in d.items(): c.execute("insert into kv values(?,?) on conflict(k) do update set v=excluded.v", ("cfg." + k, v))
        c.commit()
    finally: c.close()

def SN(): return cfg()["site_name"]
def reg_allowed(c): return c["reg_open"] == "1" or not one("select 1 from users")

def migrate(c):
    cols = {r[1] for r in c.execute("pragma table_info(users)")}
    for name, ddl in (("is_admin", "integer default 0"), ("disabled", "integer default 0"), ("last_seen", "text")):
        if name not in cols: c.execute(f"alter table users add column {name} {ddl}")
    if not c.execute("select 1 from users where is_admin=1").fetchone():
        c.execute("update users set is_admin=1 where id=(select min(id) from users)")
    adm = os.environ.get("ADMIN_USER", "").strip()
    if adm: c.execute("update users set is_admin=1 where username=?", (adm,))
    if INVITE and not c.execute("select 1 from kv where k='cfg.invite'").fetchone():
        c.execute("insert into kv values('cfg.invite',?)", (INVITE,))

# ---------------------------------------------------------------- backups
def make_backup(tag="manual"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f"claquete-{dt.datetime.now():%Y%m%d-%H%M%S}-{tag}.db")
    src, dst = db(), sqlite3.connect(path)
    try: src.backup(dst)
    finally: dst.close(); src.close()
    prune()
    return path

def list_backups():
    if not os.path.isdir(BACKUP_DIR): return []
    return [(fn, os.path.getsize(os.path.join(BACKUP_DIR, fn))) for fn in sorted(os.listdir(BACKUP_DIR), reverse=True) if re.match(BK_RE, fn)]

def prune():
    groups = {}
    for fn, _ in list_backups(): groups.setdefault(fn.rsplit("-", 1)[1][:-3], []).append(fn)
    for tag, fns in groups.items():
        for fn in fns[(14 if tag == "auto" else 20):]:
            try: os.remove(os.path.join(BACKUP_DIR, fn))
            except OSError: pass

def backup_loop():
    while True:
        try:
            day = f"claquete-{dt.date.today():%Y%m%d}-"
            if not any(fn.startswith(day) and fn.endswith("-auto.db") for fn, _ in list_backups()): make_backup("auto")
        except Exception as ex: print("ERRO backup automático:", ex, flush=True)
        time.sleep(3600)

def pl(n, w): return f"{n} {w}" if n == 1 else f"{n} {w}s"

def fsize(b):
    return f"{b / 1048576:.1f} MB".replace(".", ",") if b >= 1048576 else f"{max(1, round(b / 1024))} KB"

# ---------------------------------------------------------------- tema, logo, favicon
def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
def lum(h):
    f = lambda x: x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4
    r, g, b = (f(x / 255) for x in rgb(h)); return .2126 * r + .7152 * g + .0722 * b
def on(h): return "#fff" if lum(h) < .22 else "#0d1117"
def mixhex(h, k=.68): return "#" + "".join(f"{round(x * k + 255 * (1 - k)):02x}" for x in rgb(h))

def theme_css(c):
    if all(c[k].lower() == DEFAULTS[k] for k in COLOR_KEYS): return ""
    names = ("brand", "todo", "inv", "paid")
    def block(P):
        o = ":root{" + ";".join(f"--{n}:{v}" for n, v in P.items()) + "}"
        return o + (f".btn.p,button.p,.cell.now span,.me{{color:{on(P['brand'])}}}.chip.on.p2,.bar.paid{{color:{on(P['paid'])}}}"
                    f".chip.on.f,.bar.inv{{color:{on(P['inv'])}}}.bar.todo{{color:{on(P['todo'])}}}")
    L = dict(zip(names, (c[k] for k in COLOR_KEYS))); Dk = {n: mixhex(v) for n, v in L.items()}
    return block(L) + "@media(prefers-color-scheme:dark){" + block(Dk) + "}" + f".hero{{background:color-mix(in srgb,{L['brand']} 24%,#080b1a)}}"

def logo(c, standalone=False):
    x = ' xmlns="http://www.w3.org/2000/svg"' if standalone else ' class="lg"'
    return (f'<svg{x} viewBox="0 0 28 28"><rect width="28" height="28" rx="8" fill="{c["c_brand"]}"/><rect x="6" y="7" width="16" height="3.6" rx="1.8" fill="{c["c_todo"]}"/>'
            f'<rect x="6" y="12.2" width="11" height="3.6" rx="1.8" fill="{c["c_inv"]}"/><rect x="9" y="17.4" width="13" height="3.6" rx="1.8" fill="{c["c_paid"]}"/></svg>')

def fav(c):
    v = hashlib.sha256("".join(c[k] for k in COLOR_KEYS).encode()).hexdigest()[:6]
    return (f'<link rel="icon" type="image/svg+xml" href="/favicon.svg?v={v}"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png?v={v}">'
            f'<link rel="apple-touch-icon" href="/apple-touch-icon.png?v={v}">')

@lru_cache(maxsize=32)
def png_icon(size, cols):
    base, todo, inv, paid = (rgb(x) for x in cols)
    shapes = [(0, 0, 28, 28, 8, base), (6, 7, 16, 3.6, 1.8, todo), (6, 12.2, 11, 3.6, 1.8, inv), (9, 17.4, 13, 3.6, 1.8, paid)]
    def inside(x, y, sx, sy, w, h, r):
        if x < sx or x > sx + w or y < sy or y > sy + h: return False
        cx, cy = min(max(x, sx + r), sx + w - r), min(max(y, sy + r), sy + h - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    S, k, raw = 3, 28 / size, bytearray()
    for py in range(size):
        raw.append(0)
        for px in range(size):
            r = g = b = a = 0
            for sy in range(S):
                for sx in range(S):
                    x, y = (px + (sx + .5) / S) * k, (py + (sy + .5) / S) * k
                    col = None
                    if inside(x, y, *shapes[0][:5]):
                        col = shapes[0][5]
                        for s in shapes[1:]:
                            if inside(x, y, *s[:5]): col = s[5]
                    if col: r += col[0]; g += col[1]; b += col[2]; a += 1
            raw += bytes((r // a, g // a, b // a, 255 * a // (S * S))) if a else b"\0\0\0\0"
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))

# ---------------------------------------------------------------- publicidade (só banner de imagem ou texto)
def ad_html(c, where):
    if c["ad_on"] != "1" or c["ad_" + where] != "1": return ""
    img, link, txt = c["ad_img"], c["ad_link"], e(c["ad_text"])
    if not (img or txt): return ""
    inner = f'<img src="{e(img)}" alt="{txt}" loading="lazy" referrerpolicy="no-referrer">' if img else f"<span>{txt}</span>"
    box = f'<a class="ad" href="{e(link)}" target="_blank" rel="sponsored noopener noreferrer">{inner}</a>' if link else f'<div class="ad">{inner}</div>'
    return f'<div class="adw"><small>Publicidade</small>{box}</div>'

# ---------------------------------------------------------------- consola SQL
def sql_run(q, write):
    c = db()
    try:
        if write: make_backup("presql")
        else: c.execute("pragma query_only=1")
        cur = c.execute(q)
        if cur.description: return [d[0] for d in cur.description], cur.fetchmany(201), ""
        c.commit(); return None, None, f"Executado. Linhas alteradas: {cur.rowcount}."
    except sqlite3.Error as ex:
        m = str(ex)
        return None, None, ("Esta instrução altera dados. Marca a caixa de confirmação para a executar (é criado um backup antes)." if "readonly" in m else "Erro: " + m)
    finally: c.close()

def sql_table(cols, data):
    if cols is None: return ""
    ki = cols.index("k") if "k" in cols else -1
    def cell(r, i):
        v = r[i]
        if cols[i].lower() in ("pw", "h") or (ki >= 0 and r[ki] == "secret" and cols[i] == "v"): return "•••"
        return e("" if v is None else str(v)[:120])
    th = "".join(f'<th class="l">{e(c)}</th>' for c in cols)
    tr = "".join("<tr>" + "".join(f'<td class="l">{cell(r, i)}</td>' for i in range(len(cols))) + "</tr>" for r in data[:200])
    more = '<p class="m">A mostrar as primeiras 200 linhas.</p>' if len(data) > 200 else ""
    return f'<div class="card sc"><table class="tb"><tr>{th}</tr>{tr or "<tr><td class=l>Sem resultados.</td></tr>"}</table></div>{more}'

def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = db()
    c.executescript("""
    create table if not exists users(id integer primary key, username text unique collate nocase, email text unique collate nocase,
      name text, phone text, pw text, ics text, created text);
    create table if not exists resets(h text primary key, user_id integer references users(id) on delete cascade, exp integer);
    create table if not exists clients(id integer primary key, user_id integer not null, name text not null, nif text, contact text,
      rate text, terms text, notes text, logo text);
    create table if not exists events(id integer primary key, user_id integer not null, title text not null, start_date text not null,
      end_date text not null, client_id integer references clients(id) on delete set null, amount real default 0, invoice_date text,
      invoice_no text, paid integer default 0, paid_date text, notes text);
    create table if not exists items(id integer primary key, event_id integer references events(id) on delete cascade, label text, amount real);
    create table if not exists kv(k text primary key, v text);
    create table if not exists tickets(id integer primary key, token text unique, user_id integer, name text, email text, subject text, status text default 'open',
      lang text, created text, updated text, unread_admin integer default 1, unread_user integer default 0);
    create table if not exists friends(id integer primary key, a integer not null, b integer not null, status text default 'pending', created text, unique(a, b));
    create table if not exists chats(id integer primary key, kind text, name text, owner integer, created text);
    create table if not exists chat_members(chat_id integer references chats(id) on delete cascade, user_id integer, last_read integer default 0, primary key(chat_id, user_id));
    create table if not exists chat_msgs(id integer primary key, chat_id integer references chats(id) on delete cascade, user_id integer, body text, created text);
    create table if not exists tmsgs(id integer primary key, ticket_id integer references tickets(id) on delete cascade, from_admin integer default 0, body text, created text);""")
    if not c.execute("select 1 from kv where k='secret'").fetchone():
        c.execute("insert into kv values('secret',?)", (secrets.token_hex(32),))
    migrate(c)
    c.commit(); c.close()

def sign(s): return hmac.new(one("select v from kv where k='secret'")["v"].encode(), s.encode(), hashlib.sha256).hexdigest()
def hash_pw(p, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt, 300000).hex()
def check_pw(p, stored): return hmac.compare_digest(hash_pw(p, bytes.fromhex(stored.split("$")[0])), stored)
def session_cookie(u, secure):
    x = int(time.time()) + 30 * 86400
    return ("Set-Cookie", f"s={u['id']}.{x}.{sign(f'{u['id']}.{x}.{u['pw'][-16:]}')}; Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict" + ("; Secure" if secure else ""))

# Email: por omissao usa o Gmail. Basta definir SMTP_USER (o teu Gmail) e SMTP_PASSWORD (palavra-passe de app).
# NUNCA escrevas a palavra-passe aqui no codigo: o repositorio e publico. Define-a nas variaveis do Portainer.
def smtp_ready(): return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))

def send_mail(to, subject, body):
    try:
        user = os.environ["SMTP_USER"]; m = EmailMessage()
        m["From"] = formataddr((SN(), os.environ.get("SMTP_FROM") or user)); m["To"] = to; m["Subject"] = subject; m.set_content(body)
        h, port = os.environ.get("SMTP_HOST") or "smtp.gmail.com", int(os.environ.get("SMTP_PORT") or 587); ctx = ssl.create_default_context()
        if port == 465: s = smtplib.SMTP_SSL(h, port, timeout=20, context=ctx)
        else: s = smtplib.SMTP(h, port, timeout=20); s.starttls(context=ctx)
        s.login(user, os.environ["SMTP_PASSWORD"]); s.send_message(m); s.quit()
        print(f"Email enviado: {subject} -> {to}", flush=True)
    except Exception as ex: print("ERRO SMTP:", ex, flush=True)

def mail_async(to, subject, body):
    if smtp_ready(): threading.Thread(target=send_mail, args=(to, subject, body), daemon=True).start()

# ---------------------------------------------------------------- estilo
CSS = """
:root{--bg:#f1f3f6;--sf:#fff;--ink:#12161c;--mut:#67717e;--line:#e2e6eb;--brand:#3b4cdb;--todo:#e5484d;--inv:#f0a020;--paid:#2fa56b;--r:14px;--lh:24px}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--sf:#151b23;--ink:#e8ecf1;--mut:#8a95a3;--line:#242d38;--brand:#8c9bff;--inv:#f5b13d;--paid:#3fbf82}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",Roboto,"Helvetica Neue",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}h1{font-size:1.7rem;letter-spacing:-.03em;margin:0 0 6px;font-weight:700}h2{font-size:1.05rem;margin:28px 0 10px;letter-spacing:-.01em}
.sub{color:var(--mut);margin:0 0 20px}.m{color:var(--mut);font-size:.88rem}
.shell{display:grid;grid-template-columns:236px minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;padding:20px 14px;display:flex;flex-direction:column;gap:2px;border-right:1px solid var(--line);background:var(--sf)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:1.15rem;letter-spacing:-.02em;padding:2px 10px 20px;text-decoration:none}
.lg{width:28px;height:28px;flex:none}.sp{flex:1}
.nl{display:flex;gap:12px;align-items:center;padding:10px 12px;border-radius:10px;text-decoration:none;color:var(--mut);font-weight:560}
.nl svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
.nl:hover{color:var(--ink)}.nl.on{background:color-mix(in srgb,var(--brand) 13%,transparent);color:var(--brand)}
.nl.acct span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.top{display:none}.main{padding:30px clamp(14px,4vw,44px) 96px;max-width:1080px;width:100%}
.bar-h{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.btn,button{font:inherit;font-weight:600;padding:9px 16px;border-radius:10px;border:1px solid var(--line);background:var(--sf);color:var(--ink);cursor:pointer;text-decoration:none;display:inline-block}
.btn.p,button.p{background:var(--brand);border-color:var(--brand);color:#fff}@media(prefers-color-scheme:dark){.btn.p,button.p{color:#0d1117}}
button.d{color:var(--todo)}.chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.chips a{padding:6px 13px;border-radius:99px;border:1px solid var(--line);background:var(--sf);text-decoration:none;font-size:.88rem;color:var(--mut)}.chips a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.mn{display:flex;align-items:center;gap:8px;margin-bottom:12px}.mn b{min-width:130px;text-align:center;text-transform:capitalize}.mn a{padding:4px 12px}
.strip{display:grid;grid-template-columns:repeat(4,1fr);background:var(--sf);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.st{padding:16px 18px 14px;border-left:1px solid var(--line);border-top:3px solid var(--c,var(--line))}.st:first-child{border-left:0}
.st b{display:block;font-size:1.6rem;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1.25;margin-top:2px}.st span{color:var(--mut);font-size:.85rem}
.list{background:var(--sf);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}.list>.empty{padding:18px;color:var(--mut)}
.er{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 14px;border-top:1px solid var(--line);box-shadow:inset 3px 0 0 var(--c,transparent)}
.er:first-child{border-top:0}.todo{--c:var(--todo)}.inv{--c:var(--inv)}.paid{--c:var(--paid)}
.eh{display:flex;gap:12px;align-items:center;text-decoration:none;min-width:0;flex:1}.eh b{display:block;font-weight:620}.eh small{color:var(--mut);display:block;font-size:.85rem}
.eh>div{min-width:0}.ea{display:flex;align-items:center;gap:12px;justify-content:flex-end}.amt{font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}
.late{color:var(--todo);font-style:normal;font-weight:600}
.av{width:38px;height:38px;border-radius:10px;object-fit:contain;background:var(--bg);display:inline-grid;place-items:center;font-weight:700;font-size:.8rem;color:var(--mut);flex:none;border:1px solid var(--line)}
.tg{display:flex;gap:6px}.tg form{margin:0}.chip{font:inherit;font-size:.8rem;font-weight:600;padding:5px 11px;border-radius:99px;border:1px solid var(--line);background:none;color:var(--mut);cursor:pointer}
.chip.on.f{background:var(--inv);border-color:var(--inv);color:#1b1300}.chip.on.p2{background:var(--paid);border-color:var(--paid);color:#fff}
.card{background:var(--sf);border:1px solid var(--line);border-radius:var(--r);padding:18px;margin-bottom:14px}.card h2{margin-top:0}
form.f label{display:block;margin:14px 0 4px;font-weight:600;font-size:.86rem;color:var(--mut)}form.f label:first-child{margin-top:0}
form.f input:not([type=checkbox]),form.f select,form.f textarea{width:100%;font:inherit;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
input:focus,select:focus,textarea:focus,button:focus-visible,a:focus-visible{outline:2px solid var(--brand);outline-offset:1px}
form.f label.c{display:flex;gap:10px;align-items:center;color:var(--ink);font-size:1rem;font-weight:500}form.f input[type=checkbox]{width:20px;height:20px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.it{display:grid;grid-template-columns:1fr 140px;gap:8px;margin-bottom:8px}
.sum{display:flex;justify-content:space-between;align-items:center;padding:10px 2px;font-weight:700}.sum span{font-size:1.3rem;font-variant-numeric:tabular-nums}
.info{background:color-mix(in srgb,var(--brand) 10%,transparent);padding:10px 12px;border-radius:10px;margin-top:8px;font-size:.9rem}.info[hidden]{display:none}
details summary{cursor:pointer;color:var(--todo);margin-top:18px}.msg{padding:10px 12px;border-radius:10px;margin:0 0 14px;font-size:.92rem}.msg.err{background:color-mix(in srgb,var(--todo) 14%,transparent);color:var(--todo)}.msg.ok{background:color-mix(in srgb,var(--paid) 16%,transparent)}
.cal{background:var(--sf);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.dh,.wk{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}.dh div{padding:9px 8px;color:var(--mut);font-size:.8rem;font-weight:600;border-left:1px solid var(--line)}.dh div:first-child{border-left:0}.dh{border-bottom:1px solid var(--line)}
.wk{min-height:98px;border-top:1px solid var(--line)}.wk:nth-of-type(2){border-top:0}
.cell{border-left:1px solid var(--line);padding:6px 8px;text-decoration:none;font-size:.82rem;font-weight:600}.cell.c0{border-left:0}.cell:hover{background:color-mix(in srgb,var(--brand) 7%,transparent)}
.cell.we{background:color-mix(in srgb,var(--bg) 55%,transparent)}.cell.out{opacity:.45}.cell.now span{background:var(--brand);color:#fff;border-radius:99px;padding:2px 8px}
@media(prefers-color-scheme:dark){.cell.now span{color:#0d1117}}
.bar{z-index:1;height:calc(var(--lh) - 2px);line-height:calc(var(--lh) - 2px);margin:1px 0;padding:0 8px;font-size:.78rem;font-weight:600;color:#fff;text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:var(--c)}
.bar.inv{color:#1b1300}.bar.cs{border-radius:7px 0 0 7px;margin-left:5px}.bar.ce{border-radius:0 7px 7px 0;margin-right:5px}.bar.cs.ce{border-radius:7px}
.lgd{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0}.lgd span:before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--c);margin-right:6px}
.ch{width:100%;height:auto}.ch text{fill:var(--mut);font-size:11px}.ch .gl{stroke:var(--line)}.ch .b1{fill:var(--brand)}.ch .b2{fill:var(--paid)}
.hb{display:grid;grid-template-columns:minmax(70px,170px) 1fr auto;gap:10px;align-items:center;padding:5px 0}.hb .t{background:var(--bg);border-radius:99px;height:10px}.hb i{display:block;height:10px;border-radius:99px;background:var(--brand)}.hb b{font-variant-numeric:tabular-nums;font-size:.9rem}
.sc{overflow-x:auto}.tb{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}.tb th,.tb td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}.tb th:first-child,.tb td:first-child{text-align:left}.tb th{color:var(--mut);font-weight:600;font-size:.82rem}
.tb tr.best td{background:color-mix(in srgb,var(--paid) 12%,transparent)}.tb tr.worst td{background:color-mix(in srgb,var(--todo) 10%,transparent)}
.auth{display:grid;grid-template-columns:1.15fr 1fr;min-height:100vh}.hero{background:#0f1635;color:#e9edff;padding:clamp(28px,6vw,72px);display:flex;flex-direction:column;justify-content:center;gap:22px}
.hero h1{font-size:clamp(1.9rem,3.4vw,2.9rem);line-height:1.1;max-width:15em;margin:0}.hero p{color:#aab4e6;max-width:30em;margin:0}.hero .brand{padding:0}
.tl{display:grid;gap:8px;margin-top:8px}.tl div{position:relative;height:34px;background:#18214a;border-radius:8px}.tl i{position:absolute;top:4px;bottom:4px;border-radius:6px;font:600 .75rem/26px inherit;font-style:normal;padding:0 9px;color:#fff;overflow:hidden;white-space:nowrap;background:var(--c)}.tl i.inv{color:#1b1300}
.hero .lgd{color:#aab4e6;font-size:.85rem}.ap{display:grid;place-items:center;padding:28px 18px}.ac{width:100%;max-width:400px}.ac h1{font-size:1.5rem}.ac .l2{margin-top:16px;text-align:center}.ac .l2 a{color:var(--brand)}
@media(max-width:820px){.shell{display:block}.top{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--sf);border-bottom:1px solid var(--line)}.top .brand{padding:0}
.me{width:34px;height:34px;border-radius:99px;background:var(--brand);color:#fff;display:grid;place-items:center;font-weight:700;font-size:.8rem;text-decoration:none}
.side{position:fixed;top:auto;bottom:0;left:0;right:0;height:auto;flex-direction:row;padding:4px 4px calc(4px + env(safe-area-inset-bottom));border-top:1px solid var(--line);border-right:0;z-index:20}
.side .brand,.side .sp,.side .acct{display:none}.nl{flex:1;flex-direction:column;gap:1px;padding:6px 2px;font-size:.68rem;align-items:center;text-align:center}
.main{padding-top:18px}.strip{grid-template-columns:1fr 1fr}.st:nth-child(3){border-left:0}.st:nth-child(n+3){border-top:3px solid var(--c)}.st b{font-size:1.3rem}
.er{flex-wrap:wrap}.ea{width:100%;justify-content:space-between}:root{--lh:20px}.bar{font-size:.68rem;padding:0 4px}.cell{padding:3px 4px;font-size:.74rem}.wk{min-height:84px}
.auth{grid-template-columns:1fr}.hero{padding:24px 18px;gap:12px}.hero .tl,.hero .lgd,.hero p{display:none}.hero h1{font-size:1.5rem}.g2{grid-template-columns:1fr}.it{grid-template-columns:1fr 110px}.hb{grid-template-columns:90px 1fr auto}}
"""

CSS += """
.adw{margin:0 0 18px}.adw small{display:block;color:var(--mut);font-size:.7rem;margin-bottom:3px}
.ad{display:block;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--sf);text-decoration:none;text-align:center}
.ad img{display:block;margin:0 auto;max-width:100%;max-height:120px;object-fit:contain}.ad span{display:block;padding:12px 14px;font-weight:600}
.tb td.l,.tb th.l{text-align:left}.tb td a{text-decoration:none}
.bd{font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:99px;background:var(--line);color:var(--mut)}
.bd.a{background:color-mix(in srgb,var(--brand) 18%,transparent);color:var(--brand)}.bd.s{background:color-mix(in srgb,var(--todo) 18%,transparent);color:var(--todo)}
.g4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}form.f .g4 input[type=color]{padding:3px;height:44px;cursor:pointer}
.pre{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.pre button{font-size:.85rem;padding:6px 12px}
code,textarea.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88rem}
.bk{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:9px 0;border-top:1px solid var(--line)}.bk:first-of-type{border-top:0}
.row2{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.row2 form{margin:0}
@media(max-width:820px){.g4{grid-template-columns:1fr 1fr}}
.lang{display:flex;gap:5px;justify-content:center;flex-wrap:wrap}.lang a{font-size:.75rem;font-weight:700;padding:3px 9px;border-radius:99px;border:1px solid var(--line);text-decoration:none;color:var(--mut)}
.lang a:hover{color:var(--ink)}.lang a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}.lang.full{justify-content:flex-start}.lang.full a{font-size:.9rem;padding:7px 14px}
.ft{margin-top:40px;display:flex;flex-direction:column;gap:12px;align-items:center;text-align:center}.fl{display:flex;gap:18px}.fl a{color:var(--mut);text-decoration:none;font-size:.9rem;font-weight:560}.fl a:hover{color:var(--ink)}
.flag{width:18px;height:12px;vertical-align:-1px;border-radius:2px}.pub{max-width:660px;margin:0 auto;padding:28px clamp(14px,4vw,24px) 40px}.pub .brand{padding-left:0}
.btn.sup{width:100%;text-align:center}.btn.sup svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;vertical-align:-3px;margin-right:6px}
.msgs{display:flex;flex-direction:column;gap:10px;margin:16px 0}.mg{max-width:90%;padding:10px 14px;border-radius:14px;background:var(--sf);border:1px solid var(--line);white-space:pre-wrap;overflow-wrap:anywhere}
.mg.a{align-self:flex-end;background:color-mix(in srgb,var(--brand) 12%,var(--sf));border-color:color-mix(in srgb,var(--brand) 30%,var(--line))}.mg small{display:block;color:var(--mut);font-size:.75rem;margin-bottom:2px}
.nl{position:relative}.nb{background:var(--todo);color:#fff;border-radius:99px;font-size:.68rem;font-weight:700;padding:0 6px;min-width:18px;text-align:center;line-height:18px;font-style:normal;margin-left:auto}
@media(max-width:820px){.nl .nb{position:absolute;top:1px;left:calc(50% + 6px);margin:0}}
.chatbox{height:min(58vh,520px);overflow:auto;margin:14px 0;padding:4px 2px}.chatbox .msgs{margin:0}.row2 input[type=text],.row2 input:not([type]){flex:1;min-width:180px}
.ab li{margin:7px 0}.ab ul{padding-left:20px;margin:6px 0}.cr{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
"""

IC = {"home": '<path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
      "cal": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
      "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
      "users": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
      "chart": '<path d="M5 20V11M12 20V4M19 20v-6"/>',
      "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>'}
NAV = [("/", "Início", "home"), ("/calendar", "Calendário", "cal"), ("/events", "Eventos", "list"), ("/clients", "Clientes", "users"), ("/chat", "Chat", "chat"), ("/stats", "Estatísticas", "chart")]
IC["shield"] = '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>'
IC["chat"] = '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>'
FLAG = ('<svg class="flag" viewBox="0 0 30 20" role="img" aria-label="Portugal"><rect width="30" height="20" fill="#d4202c"/><rect width="12" height="20" fill="#046a38"/>'
        '<circle cx="12" cy="10" r="4" fill="#ffd400" stroke="#fff" stroke-width=".7"/></svg>')
SUPBTN = f'<p class="l2"><a class="btn sup" href="/support"><svg viewBox="0 0 24 24">{IC["chat"]}</svg>Suporte</a></p>'

def langbar(full=False):
    cur, nx = i18n.lang(), quote(i18n.path(), safe="")
    return (f'<div class="lang{" full" if full else ""}">' + "".join(
        f'<a href="/lang?l={k}&amp;next={nx}" hreflang="{k}"{" class=on aria-current=true" if k == cur else ""}>{v if full else k.upper()}</a>' for k, v in i18n.LANGS.items()) + "</div>")

def foot(n=0):
    b = f' <span class="bd s">{n}</span>' if n else ""
    return (f'<footer class="ft">{langbar()}<div class="fl"><a href="/support">Suporte{b}</a><a href="/about">Sobre</a></div>'
            f'<div class="m">Feito por Daniel Nunes · Made in Portugal {FLAG}</div></footer>')

def head(t, c):
    return ('<!doctype html><html lang="' + i18n.lang() + '"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="'
            + c["c_brand"] + '"><title>' + t + '</title>' + fav(c) + '<style>' + CSS + theme_css(c) + '</style></head><body>')

def page(title, body, active, u):
    c = cfg(); sn = e(c["site_name"]); lg = logo(c)
    cb = chat_badge(u["id"])
    nav = "".join(f'<a class="nl{" on" if h == active else ""}" href="{h}"><svg viewBox="0 0 24 24">{IC[i]}</svg><span>{n}</span>{f"<i class=nb>{cb}</i>" if cb and h == "/chat" else ""}</a>' for h, n, i in NAV)
    adm = f'<a class="nl acct{" on" if active == "/admin" else ""}" href="/admin"><svg viewBox="0 0 24 24">{IC["shield"]}</svg><span>Admin</span></a>' if u["is_admin"] else ""
    madm = '<a class="btn" style="padding:4px 12px" href="/admin">Admin</a>' if u["is_admin"] else ""
    nu = one("select count(*) from tickets where user_id=? and unread_user=1", (u["id"],))[0]
    madm += f'<a class="btn" style="padding:4px 12px" href="/support">💬 {nu}</a>' if nu else ""
    acct = f'<a class="nl acct{" on" if active == "/settings" else ""}" href="/settings"><svg viewBox="0 0 24 24">{IC["gear"]}</svg><span>{e(u["name"] or u["username"])}</span></a>'
    top = (f'<div class="top"><a class="brand" href="/">{lg}{sn}</a><div style="display:flex;gap:10px;align-items:center">{madm}'
           f'<a class="me" href="/settings" aria-label="Conta">{e(ini(u["name"] or u["username"]))}</a></div></div>')
    return (head(eh(title) + " · " + sn, c) + f'<div class="shell"><nav class="side"><a class="brand" href="/">{lg}{sn}</a>{nav}<div class="sp"></div>{adm}{acct}</nav>'
            f'<div>{top}<main class="main">{ad_html(c, "app")}{body}{foot(nu)}</main></div></body></html>')

TL = ('<div class="tl"><div><i class="paid" style="left:2%;width:30%">Casamento</i><i class="inv" style="left:38%;width:24%">Conferência</i></div>'
      '<div><i class="todo" style="left:12%;width:26%">Videoclip</i><i class="paid" style="left:46%;width:40%">Festival · 3 dias</i></div>'
      '<div><i class="inv" style="left:0;width:20%">Spot</i><i class="todo" style="left:44%;width:30%">Institucional</i></div></div>'
      '<div class="lgd"><span style="--c:var(--todo)">por faturar</span><span style="--c:var(--inv)">faturada</span><span style="--c:var(--paid)">paga</span></div>')

def auth_page(title, inner):
    c = cfg(); sn = e(c["site_name"]); lg = logo(c)
    ht = eh(c["hero_title"]) if c["hero_title"] == DEFAULTS["hero_title"] else e(c["hero_title"])
    hx = eh(c["hero_text"]) if c["hero_text"] == DEFAULTS["hero_text"] else e(c["hero_text"])
    return (head(eh(title) + " · " + sn, c) + f'<div class="auth"><section class="hero"><a class="brand" href="/">{lg}{sn}</a>'
            f'<h1>{ht}</h1><p>{hx}</p>{TL}</section><section class="ap"><div class="ac">{inner}{ad_html(c, "auth")}{foot()}</div></section></div></body></html>')

def pub_page(title, body):
    c = cfg(); sn = e(c["site_name"]); lg = logo(c)
    return head(eh(title) + " · " + sn, c) + f'<div class="pub"><a class="brand" href="/">{lg}{sn}</a><main>{ad_html(c, "auth")}{body}{foot()}</main></div></body></html>'

def uname(r): return (r["name"] or r["username"]) if r else "?"

def friends_of(uid):
    return rows("select u.* from friends f join users u on u.id = case when f.a=? then f.b else f.a end where f.status='ok' and (f.a=? or f.b=?) and u.disabled=0 order by lower(coalesce(nullif(u.name,''),u.username))", (uid, uid, uid))

def chat_member(cid, uid): return one("select * from chat_members where chat_id=? and user_id=?", (cid, uid))

def dm_chat(a, b):
    r = one("select c.id from chats c join chat_members x on x.chat_id=c.id and x.user_id=? join chat_members y on y.chat_id=c.id and y.user_id=? where c.kind='dm'", (a, b))
    if r: return r["id"]
    cid = run("insert into chats(kind,name,owner,created) values('dm','',?,?)", (a, now_str()))
    run("insert into chat_members(chat_id,user_id) values(?,?)", (cid, a)); run("insert into chat_members(chat_id,user_id) values(?,?)", (cid, b))
    return cid

def chat_badge(uid):
    un = one("select count(*) from chat_msgs m join chat_members cm on cm.chat_id=m.chat_id and cm.user_id=? where m.id>cm.last_read and m.user_id!=?", (uid, uid))[0]
    return un + one("select count(*) from friends where b=? and status='pending'", (uid,))[0]

def purge_user(tid):
    run("delete from events where user_id=?", (tid,)); run("delete from clients where user_id=?", (tid,)); run("delete from tickets where user_id=?", (tid,))
    run("delete from friends where a=? or b=?", (tid, tid))
    run("delete from chats where kind='dm' and id in (select chat_id from chat_members where user_id=?)", (tid,))
    run("delete from chat_msgs where user_id=?", (tid,))
    run("update chats set owner=(select user_id from chat_members where chat_id=chats.id and user_id!=? limit 1) where owner=?", (tid, tid))
    run("delete from chat_members where user_id=?", (tid,))
    run("delete from chats where id not in (select chat_id from chat_members)")
    run("delete from users where id=?", (tid,))

def shell(title, body, u, active=""): return page(title, body, active, u) if u else pub_page(title, body)

def notify_admins(subject, text):
    if smtp_ready():
        for r in rows("select email from users where is_admin=1 and disabled=0"): mail_async(r["email"], subject, text)

def fld(label, name, typ="text", val="", extra=""):
    return f'<label>{label}</label><input name="{name}" type="{typ}" value="{e(val)}" {extra}>'

# ---------------------------------------------------------------- componentes
EV = "select e.*, c.name cn, c.logo cl from events e left join clients c on c.id=e.client_id "
def state(r): return "paid" if r["paid"] else "inv" if r["invoice_date"] else "todo"

def avatar(name, logo):
    if logo: return f'<img class="av" src="{e(logo)}" alt="" referrerpolicy="no-referrer" loading="lazy">'
    return f'<span class="av">{e(ini(name))}</span>'

def tog(r, nxt):
    def b(f, label, on, cl):
        return f'<form method="post" action="/toggle/{r["id"]}/{f}"><input type="hidden" name="next" value="{e(nxt)}"><button class="chip {cl}{" on" if on else ""}">{"✓ " if on else ""}{label}</button></form>'
    return '<div class="tg">' + b("invoiced", "Faturada", r["invoice_date"], "f") + b("paid", "Paga", r["paid"], "p2") + "</div>"

def ev_row(r, nxt):
    meta = f'{drange(r["start_date"], r["end_date"])} · {(e(r["cn"]) if r["cn"] else "sem cliente")}'
    if r["invoice_date"]: meta += f' · faturada {ds(r["invoice_date"])}'
    elif r["end_date"] < today().isoformat(): meta += ' · <em class="late">terminou, falta faturar</em>'
    return (f'<div class="er {state(r)}"><a class="eh" href="/event/{r["id"]}">{avatar(r["cn"] or "?", r["cl"])}<div><b>{e(r["title"])}</b><small>{meta}</small></div></a>'
            f'<div class="ea"><span class="amt">{eur(r["amount"])}</span>{tog(r, nxt)}</div></div>')

def lst(rs, nxt, empty): return '<div class="list">' + ("".join(ev_row(r, nxt) for r in rs) or f'<div class="empty">{empty}</div>') + "</div>"

# ---------------------------------------------------------------- servidor
class H(BaseHTTPRequestHandler):
    fails = {}
    def log_message(self, *a): pass

    def user(self):
        m = cookies.SimpleCookie(self.headers.get("Cookie", "")).get("s")
        try:
            i, x, sig = m.value.split("."); u = one("select * from users where id=?", (i,))
            if u and not u["disabled"] and int(x) > time.time() and hmac.compare_digest(sig, sign(f"{i}.{x}.{u['pw'][-16:]}")):
                now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                if (u["last_seen"] or "")[:15] != now[:15]: run("update users set last_seen=? where id=?", (now, u["id"]))
                return u
        except Exception: pass
        return None

    def https(self): return self.headers.get("X-Forwarded-Proto") == "https"

    def pick_lang(self):
        m = cookies.SimpleCookie(self.headers.get("Cookie", "")).get("lang")
        return m.value if m and m.value in i18n.LANGS else i18n.best_accept(self.headers.get("Accept-Language"), cfg()["lang"])

    def out(self, body, code=200, ctype="text/html; charset=utf-8", hd=()):
        if isinstance(body, str) and ctype.startswith("text/html"): body = i18n.finish(body)
        n = secrets.token_urlsafe(12); b = body if isinstance(body, bytes) else body.replace("__NONCE__", n).encode(); self.send_response(code)
        for k, v in (("Content-Type", ctype), ("Content-Length", str(len(b))), ("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "same-origin"),
                     ("Content-Security-Policy", f"default-src 'self'; style-src 'unsafe-inline'; script-src 'nonce-{n}'; img-src 'self' https: data:; form-action 'self'; frame-ancestors 'none'"), *hd):
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def go(self, to, hd=()):
        self.send_response(303); self.send_header("Location", to)
        for k, v in hd: self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        u_ = urlparse(self.path); q = parse_qs(u_.query); p = u_.path; g = lambda k, d="": q.get(k, [d])[0]
        i18n.set_lang(self.pick_lang(), self.path)
        if p == "/lang":
            nx = g("next", "/"); nx = nx if nx.startswith("/") and not nx.startswith("//") else "/"
            ck = f"lang={g('l')}; Max-Age=31536000; Path=/; SameSite=Lax" + ("; Secure" if self.https() else "")
            return self.go(nx, [("Set-Cookie", ck)] if g("l") in i18n.LANGS else [])
        if p == "/calendar.ics": return self.ics(g("k"))
        if p in ("/favicon.svg", "/favicon.ico", "/favicon-32.png", "/apple-touch-icon.png"): return self.icon(p)
        u = self.user()
        if p in ("/login", "/register", "/forgot", "/reset"):
            if u: return self.go("/")
            return self.out({"/login": lambda: self.login_page(ok=g("ok")), "/register": self.register_page, "/forgot": self.forgot_page, "/reset": lambda: self.reset_page(g("t"))}[p]())
        if p == "/about" or p.startswith("/support"):
            try: return self.out(self.about(u) if p == "/about" else self.support_get(u, p, g))
            except (ValueError, KeyError, IndexError): return self.out(shell("Não encontrado", "<h1>Página não encontrada</h1>", u), 404)
        if not u: return self.go("/login")
        parts = p.strip("/").split("/")
        try:
            if parts[0] == "admin": return self.admin_get(u, p, parts, g)
            if parts[0] == "chat": return self.chat_get(u, p, parts, g)
            if p == "/": return self.out(self.home(u, g("m")))
            if p == "/calendar": return self.out(self.cal(u, g("m")))
            if p == "/events": return self.out(self.events(u, g("f", "todos")))
            if p == "/clients": return self.out(self.clients(u))
            if p == "/stats": return self.out(self.stats(u, g("y")))
            if p == "/settings": return self.out(self.settings(u, ok=g("ok")))
            if parts[0] == "event" and len(parts) == 2: return self.out(self.event_form(u, parts[1], g("date")))
            if parts[0] == "client" and len(parts) == 2: return self.out(self.client_form(u, parts[1]))
        except (ValueError, KeyError, TypeError): pass
        self.out(page("Não encontrado", "<h1>Página não encontrada</h1>", "", u), 404)

    def do_POST(self):
        i18n.set_lang(self.pick_lang(), "/")
        org, sf = self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site")
        hosts = (self.headers.get("Host"), self.headers.get("X-Forwarded-Host"))
        if sf == "cross-site" or (not sf and org not in (None, "null") and urlparse(org).netloc not in hosts): return self.out("Pedido recusado", 403, "text/plain")
        if urlparse(self.path).path == "/admin/db/restore": return self.restore()
        n = int(self.headers.get("Content-Length", 0) or 0)
        self.fl = parse_qs(self.rfile.read(min(n, 200000)).decode(), keep_blank_values=True); f = {k: v[0] for k, v in self.fl.items()}
        p = urlparse(self.path).path; parts = p.strip("/").split("/")
        if p.startswith("/support"):
            try: return self.support_post(self.user(), p, f)
            except (ValueError, KeyError, IndexError): return self.out(shell("Não encontrado", "<h1>Página não encontrada</h1>", self.user()), 404)
        pub = {"/login": self.do_login, "/register": self.do_register, "/forgot": self.do_forgot, "/reset": self.do_reset}
        if p in pub: return pub[p](f)
        u = self.user()
        if not u: return self.go("/login")
        if p == "/logout": return self.go("/login", [("Set-Cookie", "s=; Max-Age=0; Path=/")])
        if parts[0] == "admin": return self.admin_post(u, p, parts, f)
        if parts[0] == "chat":
            try: return self.chat_post(u, p, parts, f)
            except (ValueError, KeyError, IndexError): return self.go("/chat")
        i = u["id"]; nxt = f.get("next", "/"); nxt = nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"
        if parts[0] == "toggle" and len(parts) == 3:
            r = one("select * from events where id=? and user_id=?", (parts[1], i)); t = today().isoformat()
            if r and parts[2] == "invoiced":
                if r["invoice_date"]: run("update events set invoice_date=null, paid=0, paid_date=null where id=?", (r["id"],))
                else: run("update events set invoice_date=? where id=?", (t, r["id"]))
            elif r and parts[2] == "paid":
                if r["paid"]: run("update events set paid=0, paid_date=null where id=?", (r["id"],))
                else: run("update events set paid=1, paid_date=?, invoice_date=coalesce(invoice_date,?) where id=?", (t, t, r["id"]))
            return self.go(nxt)
        if p == "/event/save": return self.save_event(u, f)
        if parts[0] == "event" and len(parts) == 3 and parts[2] == "delete":
            run("delete from events where id=? and user_id=?", (parts[1], i)); return self.go("/events")
        if p == "/client/save":
            v = tuple(f.get(k, "").strip()[:300] for k in ("name", "nif", "contact", "rate", "terms", "notes"))
            logo = f.get("logo", "").strip(); logo = logo if re.match(r"^https?://", logo) else ""
            if not v[0]: return self.go("/clients")
            if f.get("id") and one("select 1 from clients where id=? and user_id=?", (f["id"], i)):
                run("update clients set name=?,nif=?,contact=?,rate=?,terms=?,notes=?,logo=? where id=? and user_id=?", v + (logo, f["id"], i))
            else: run("insert into clients(user_id,name,nif,contact,rate,terms,notes,logo) values(?,?,?,?,?,?,?,?)", (i,) + v + (logo,))
            return self.go("/clients")
        if parts[0] == "client" and len(parts) == 3 and parts[2] == "delete":
            run("delete from clients where id=? and user_id=?", (parts[1], i)); return self.go("/clients")
        if p == "/settings/ics": run("update users set ics=? where id=?", (secrets.token_hex(20), i)); return self.go("/settings?ok=ics")
        if p == "/settings/profile": return self.save_profile(u, f)
        if p == "/settings/password": return self.save_password(u, f)
        self.go("/")

    # ---- autenticação
    def login_page(self, err="", ok=""):
        msg = f'<p class="msg err">{err}</p>' if err else '<p class="msg ok">Palavra-passe alterada. Já podes entrar.</p>' if ok == "reset" else ""
        return auth_page("Entrar", f'<h1>Entrar</h1><p class="sub">Bem-vindo de volta.</p>{msg}<form class="f" method="post" action="/login">'
            + fld("Utilizador ou email", "u", extra='autocomplete="username" required autofocus') + fld("Palavra-passe", "p", "password", extra='autocomplete="current-password" required')
            + '<p><button class="p" style="width:100%">Entrar</button></p></form><p class="l2"><a href="/forgot">Esqueci-me da palavra-passe</a></p><p class="l2 m">Ainda não tens conta? <a href="/register">Criar conta</a></p>' + SUPBTN)

    def do_login(self, f):
        ip = self.client_address[0]; n, t = self.fails.get(ip, (0, 0))
        if n >= 8 and time.time() - t < 300: return self.out(self.login_page("Demasiadas tentativas. Espera 5 minutos."), 429)
        x = f.get("u", "").strip(); u = one("select * from users where username=? or email=?", (x, x))
        if u and check_pw(f.get("p", ""), u["pw"]):
            if u["disabled"]: return self.out(self.login_page("Esta conta está suspensa. Fala com o administrador."), 403)
            self.fails.pop(ip, None); return self.go("/", [session_cookie(u, self.https())])
        self.fails[ip] = (n + 1, time.time()); self.out(self.login_page("Utilizador ou palavra-passe incorretos."), 401)

    def register_page(self, err="", v=None):
        v = v or {}; c = cfg()
        if not reg_allowed(c): return auth_page("Registo fechado", '<h1>Registo fechado</h1><p class="sub">De momento não estão a ser criadas contas novas.</p><p class="l2"><a href="/login">Entrar</a></p>')
        inv = fld("Código de convite", "code", extra="required") if c["invite"] and one("select 1 from users") else ""
        return auth_page("Criar conta", '<h1>Criar conta</h1><p class="sub">Demora menos de um minuto.</p>' + (f'<p class="msg err">{err}</p>' if err else "") + '<form class="f" method="post" action="/register">'
            + fld("Utilizador", "u", val=v.get("u", ""), extra='autocomplete="username" required autofocus') + fld("Email (para recuperar a palavra-passe)", "email", "email", v.get("email", ""), 'autocomplete="email" required')
            + fld("Palavra-passe (mínimo 8 caracteres)", "p", "password", extra='autocomplete="new-password" minlength="8" required') + fld("Repetir palavra-passe", "p2", "password", extra='autocomplete="new-password" minlength="8" required')
            + inv + '<p><button class="p" style="width:100%">Criar conta e entrar</button></p></form><p class="l2 m">Já tens conta? <a href="/login">Entrar</a></p>' + SUPBTN)

    def do_register(self, f):
        v = {"u": f.get("u", "").strip(), "email": f.get("email", "").strip()}; err = ""
        c = cfg()
        if not reg_allowed(c): err = "O registo está fechado."
        elif c["invite"] and one("select 1 from users") and not hmac.compare_digest(f.get("code", ""), c["invite"]): err = "Código de convite incorreto."
        elif not re.match(r"^[\w.\-]{3,30}$", v["u"]): err = "O utilizador deve ter 3 a 30 caracteres (letras, números, . _ -)."
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v["email"]): err = "Email inválido."
        elif len(f.get("p", "")) < 8: err = "A palavra-passe tem de ter pelo menos 8 caracteres."
        elif f.get("p") != f.get("p2"): err = "As palavras-passe não coincidem."
        if not err:
            try:
                first = 0 if one("select 1 from users") else 1
                uid = run("insert into users(username,email,name,pw,ics,created,is_admin) values(?,?,?,?,?,?,?)", (v["u"], v["email"], v["u"], hash_pw(f["p"]), secrets.token_hex(20), today().isoformat(), first))
            except sqlite3.IntegrityError: err = "Esse utilizador ou email já está registado."
        if err: return self.out(self.register_page(err, v), 400)
        mail_async(v["email"], i18n.mail("welcome_s", site=SN()), i18n.mail("welcome_b", name=v["u"], site=SN(), user=v["u"], enter=i18n.mail("enter", url=BASE_URL) if BASE_URL else ""))
        self.go("/", [session_cookie(one("select * from users where id=?", (uid,)), self.https())])

    def forgot_page(self, sent=False):
        if sent: return auth_page("Recuperar", '<h1>Verifica o teu email</h1><p class="sub">Se esse email estiver registado, enviámos um link para definires uma nova palavra-passe. O link é válido durante 1 hora.</p><p class="l2"><a href="/login">Voltar a entrar</a></p>')
        return auth_page("Recuperar", '<h1>Recuperar palavra-passe</h1><p class="sub">Indica o email da tua conta.</p><form class="f" method="post" action="/forgot">' + fld("Email", "email", "email", extra="required autofocus")
            + '<p><button class="p" style="width:100%">Enviar link</button></p></form><p class="l2"><a href="/login">Voltar</a></p>' + SUPBTN)

    def do_forgot(self, f):
        ip = "f" + self.client_address[0]; n, t = self.fails.get(ip, (0, 0))
        if n >= 5 and time.time() - t < 900: return self.out(self.forgot_page(True))
        self.fails[ip] = (n + 1 if time.time() - t < 900 else 1, time.time())
        u = one("select * from users where email=?", (f.get("email", "").strip(),))
        if u:
            tok = secrets.token_urlsafe(32); run("delete from resets where user_id=? or exp<?", (u["id"], time.time()))
            run("insert into resets values(?,?,?)", (hashlib.sha256(tok.encode()).hexdigest(), u["id"], int(time.time()) + 3600))
            if BASE_URL and smtp_ready():
                mail_async(u["email"], i18n.mail("reset_s", site=SN()), i18n.mail("reset_b", name=u["name"], url=f"{BASE_URL}/reset?t={tok}"))
            else: print(f"[RECUPERAÇÃO] email/BASE_URL não configurado. Link para {u['username']}: http://{self.headers.get('Host')}/reset?t={tok}", flush=True)
        self.out(self.forgot_page(True))

    def reset_page(self, tok, err=""):
        if not one("select 1 from resets where h=? and exp>?", (hashlib.sha256(tok.encode()).hexdigest(), time.time())):
            return auth_page("Link inválido", '<h1>Link inválido ou expirado</h1><p class="sub">Pede um novo link para recuperar a palavra-passe.</p><p class="l2"><a href="/forgot">Pedir novo link</a></p>')
        return auth_page("Nova palavra-passe", '<h1>Nova palavra-passe</h1>' + (f'<p class="msg err">{err}</p>' if err else "") + f'<form class="f" method="post" action="/reset"><input type="hidden" name="t" value="{e(tok)}">'
            + fld("Nova palavra-passe (mínimo 8)", "p", "password", extra='autocomplete="new-password" minlength="8" required autofocus') + fld("Repetir", "p2", "password", extra='autocomplete="new-password" minlength="8" required') + '<p><button class="p" style="width:100%">Guardar</button></p></form>')

    def do_reset(self, f):
        tok = f.get("t", ""); h = hashlib.sha256(tok.encode()).hexdigest(); r = one("select * from resets where h=? and exp>?", (h, time.time()))
        if not r: return self.out(self.reset_page(tok))
        if len(f.get("p", "")) < 8 or f.get("p") != f.get("p2"): return self.out(self.reset_page(tok, "As palavras-passe têm de coincidir e ter 8+ caracteres."), 400)
        run("update users set pw=? where id=?", (hash_pw(f["p"]), r["user_id"])); run("delete from resets where user_id=?", (r["user_id"],)); self.go("/login?ok=reset")

    def icon(self, p):
        c = cfg(); hd = (("Cache-Control", "public, max-age=86400"),)
        if p == "/favicon.svg": return self.out(logo(c, True), 200, "image/svg+xml", hd)
        size = {"/favicon.ico": 48, "/favicon-32.png": 32, "/apple-touch-icon.png": 180}[p]
        self.out(png_icon(size, tuple(c[k] for k in COLOR_KEYS)), 200, "image/png", hd)

    # ---- admin
    TABS = [("/admin", "Resumo"), ("/admin/users", "Utilizadores"), ("/admin/site", "Site"), ("/admin/ads", "Publicidade"), ("/admin/support", "Suporte"), ("/admin/db", "Base de dados")]
    FLASH = {"texts": "Textos e registo guardados.", "colors": "Cores guardadas.", "reset": "Cores repostas.", "ads": "Publicidade guardada.", "user": "Dados guardados.",
             "pw": "Palavra-passe definida. A pessoa tem de entrar de novo.", "ics": "Link do calendário renovado.", "state": "Estado atualizado.", "snap": "Backup criado.", "newadmin": "Administrador adicionado.",
             "reply": "Resposta enviada.", "closed": "Conversa fechada.", "reopened": "Conversa reaberta.", "deleted": "Conversa apagada.",
             "bulkdel": "Contas apagadas.", "nosel": "Seleciona pelo menos uma conta e marca a confirmação.", "nouser": "Não encontrámos essa conta (ou já é administradora)."}

    def apage(self, u, tab, body, ok="", err=""):
        ns = one("select count(*) from tickets where unread_admin=1")[0]
        chips = "".join(f'<a class="{"on" if h == tab else ""}" href="{h}">{n}{f" <span class=\"bd s\">{ns}</span>" if ns and h == "/admin/support" else ""}</a>' for h, n in self.TABS)
        m = f'<p class="msg ok">{eh(self.FLASH[ok])}</p>' if ok in self.FLASH else (f'<p class="msg err">{eh(err)}</p>' if err else "")
        return page("Admin", f'<div class="bar-h"><div><h1>Admin</h1><p class="sub" style="margin:0">Gestão do site, das contas e dos dados.</p></div></div><div class="chips">{chips}</div>{m}{body}', "/admin", u)

    def send_file(self, path):
        if not os.path.isfile(path): raise ValueError
        with open(path, "rb") as fh: data = fh.read()
        self.out(data, 200, "application/octet-stream", (("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"'),))

    def admin_get(self, u, p, parts, g):
        if not u["is_admin"]: raise ValueError
        if p == "/admin": return self.out(self.a_home(u))
        if p == "/admin/users": return self.out(self.a_users(u, g("ok")))
        if p == "/admin/site": return self.out(self.a_site(u, g("ok")))
        if p == "/admin/ads": return self.out(self.a_ads(u, g("ok")))
        if p == "/admin/db": return self.out(self.a_db(u, g("ok"), g("t")))
        if p == "/admin/support": return self.out(self.a_support(u, g("f", "open"), g("ok")))
        if len(parts) == 3 and parts[1] == "support": return self.out(self.a_ticket(u, parts[2], g("ok")))
        if p == "/admin/backup.db": return self.send_file(make_backup("manual"))
        if len(parts) == 3 and parts[1] == "user": return self.out(self.a_user(u, parts[2], g("ok")))
        if len(parts) == 3 and parts[1] == "backups" and re.match(BK_RE, parts[2]): return self.send_file(os.path.join(BACKUP_DIR, parts[2]))
        raise ValueError

    def a_home(self, u):
        q = lambda s, a=(): one(s, a)[0]
        wk = (today() - dt.timedelta(7)).isoformat(); c = cfg(); size = os.path.getsize(DB) if os.path.exists(DB) else 0
        tile = lambda col, lab, val, sub: f'<div class="st" style="--c:{col}"><span>{lab}</span><b>{val}</b><span>{sub}</span></div>'
        strip = ('<div class="strip">' + tile("var(--brand)", "Contas", q("select count(*) from users"), f'+{q("select count(*) from users where created>=?", (wk,))} nos últimos 7 dias')
                 + tile("var(--paid)", "Ativas (7 dias)", q("select count(*) from users where last_seen>=?", (wk,)), "com acesso recente")
                 + tile("var(--inv)", "Eventos", q("select count(*) from events"), pl(q("select count(*) from clients"), "cliente"))
                 + tile("var(--todo)", "Base de dados", fsize(size), f"{len(list_backups())} backups") + "</div>")
        w = []
        if not smtp_ready(): w.append("O envio de emails está desligado (define SMTP_USER e SMTP_PASSWORD no Portainer).")
        if not BASE_URL: w.append("BASE_URL não está definido: os links nos emails não funcionam.")
        ns = q("select count(*) from tickets where unread_admin=1")
        if c["reg_open"] == "1" and not c["invite"]: w.append("Qualquer pessoa com o endereço do site pode criar conta. Define um código de convite em Site.")
        wl = [f"<li>{eh(x)}</li>" for x in w] + ([f'<li><a href="/admin/support">{eh("Mensagens de suporte por ler:")} <b>{ns}</b></a></li>'] if ns else [])
        wh = ("<ul style='margin:0;padding-left:20px'>" + "".join(wl) + "</ul>") if wl else '<p class="m" style="margin:0">Tudo em ordem.</p>'
        rec = "".join(f'<div class="er"><a class="eh" href="/admin/user/{x["id"]}"><span class="av">{e(ini(x["name"] or x["username"]))}</span><div><b>{e(x["name"] or x["username"])}</b>'
                      f'<small>{e(x["email"])} · registo {e(x["created"])}</small></div></a><span class="m">{e(x["last_seen"]) if x["last_seen"] else "nunca entrou"}</span></div>' for x in rows("select * from users order by id desc limit 6"))
        return self.apage(u, "/admin", f'{strip}<h2>Avisos</h2><div class="card">{wh}</div><h2>Últimas contas</h2><div class="list">{rec}</div><p><a class="btn" href="/admin/users">Ver todas as contas</a></p>')

    def a_users(self, u, ok=""):
        us = rows("select u.*, (select count(*) from events where user_id=u.id) ne, (select count(*) from clients where user_id=u.id) nc from users u order by id")
        bd = lambda x: ('<span class="bd a">Admin</span> ' if x["is_admin"] else "") + ('<span class="bd s">Suspensa</span>' if x["disabled"] else "")
        chk = lambda x: "" if x["id"] == u["id"] else f'<input type="checkbox" name="ids" value="{x["id"]}">'
        tr = "".join(f'<tr class="ur"><td>{chk(x)}</td><td><a href="/admin/user/{x["id"]}"><b>{e(x["name"] or x["username"])}</b></a><br><span class="m">@{e(x["username"])}</span></td><td class="l">{e(x["email"])}</td>'
                     f'<td>{e(x["created"])}</td><td>{e(x["last_seen"]) if x["last_seen"] else "nunca"}</td><td>{x["ne"]}</td><td>{x["nc"]}</td><td>{bd(x)}</td></tr>' for x in us)
        cand = "".join(f'<option value="{e(x["username"])}">{e(x["name"] or x["username"])} · {e(x["email"])}</option>' for x in us if not x["is_admin"] and not x["disabled"])
        adm = ", ".join(f'<a href="/admin/user/{x["id"]}"><b>{e(x["name"] or x["username"])}</b></a>' for x in us if x["is_admin"])
        addf = ('<form class="f card" method="post" action="/admin/users/promote"><h2>Administradores</h2><p class="m">Atuais: ' + adm + '. Os administradores veem e gerem todas as contas e dados. '
                'Para adicionar alguém, essa pessoa tem de ter criado conta primeiro.</p>'
                + (f'<label>Adicionar administrador</label><div class="row2"><input name="q" list="ulist" autocomplete="off" placeholder="Escreve o utilizador ou email" required><datalist id="ulist">{cand}</datalist><button class="p">Tornar admin</button></div>'
                    '<p class="m">Escreve parte do nome, utilizador ou email e escolhe da lista.</p>' if cand
                   else '<p class="m">Não há mais contas para promover.</p>') + '</form>')
        return self.apage(u, "/admin/users", addf + f'<p class="m">{len(us)} contas. Clica num nome para editar, mudar o email, repor a palavra-passe ou suspender.</p>'
                          '<input id="uf" placeholder="Procurar na lista..." style="margin-bottom:10px;width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--sf);color:var(--ink);font:inherit" autocomplete="off">'
                          f'<form method="post" action="/admin/users/bulkdelete"><div class="card sc"><table class="tb" id="ut"><tr><th></th><th>Conta</th><th class="l">Email</th><th>Registo</th><th>Último acesso</th><th>Eventos</th><th>Clientes</th><th></th></tr>{tr}</table></div>'
                          '<div class="card"><h2 style="margin-top:0">Apagar contas selecionadas</h2><label class="c"><input type="checkbox" name="confirm">Confirmo: apagar as contas selecionadas e todos os seus dados (é feito um backup antes)</label>'
                          '<p><button class="d">Apagar contas selecionadas</button></p></div></form>'
                          '<script nonce="__NONCE__">document.getElementById("uf").oninput=function(){var q=this.value.toLowerCase();document.querySelectorAll("#ut tr.ur").forEach(function(r){r.style.display=r.textContent.toLowerCase().indexOf(q)<0?"none":""})}</script>', ok)

    def a_user(self, u, tid, ok="", err="", link=""):
        t = one("select * from users where id=?", (tid,))
        if not t: raise ValueError
        ne = one("select count(*) from events where user_id=?", (t["id"],))[0]; nc = one("select count(*) from clients where user_id=?", (t["id"],))[0]
        me = t["id"] == u["id"]; base = f"/admin/user/{t['id']}"
        bdg = ('<span class="bd a">Admin</span> ' if t["is_admin"] else "") + ('<span class="bd s">Suspensa</span>' if t["disabled"] else "")
        btn = lambda act, label, cls="": f'<form method="post" action="{base}/{act}"><button class="{cls}">{label}</button></form>'
        lk = (f'<div class="card"><b>Link de recuperação (válido 1 hora)</b><p class="m">Envia este link à pessoa para ela escolher uma nova palavra-passe.</p>'
              f'<input readonly id="lk" value="{e(link)}" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)"></div>') if link else ""
        return self.apage(u, "/admin/users", (
            f'<p><a href="/admin/users" class="m">‹ Todas as contas</a></p>{lk}'
            f'<div class="card"><div class="row2"><span class="av">{e(ini(t["name"] or t["username"]))}</span><div><b>{e(t["name"] or t["username"])}</b> {bdg}'
            f'<div class="m">Registo {e(t["created"])} · último acesso {e(t["last_seen"]) if t["last_seen"] else "nunca"} · {pl(ne, "evento")} · {pl(nc, "cliente")}</div></div></div></div>'
            f'<form class="f card" method="post" action="{base}/save"><h2>Dados da conta</h2>' + fld("Utilizador", "username", val=t["username"], extra="required") + fld("Nome", "name", val=t["name"], extra="required")
            + fld("Email", "email", "email", t["email"], "required") + fld("Telemóvel", "phone", "tel", t["phone"] or "") + '<p><button class="p">Guardar</button></p></form>'
            f'<div class="card"><h2>Acesso</h2><div class="row2">{btn("link", "Gerar link de recuperação")}{btn("ics", "Renovar link do calendário")}</div>'
            f'<form class="f" method="post" action="{base}/password" style="margin-top:14px"><label>Definir nova palavra-passe (mínimo 8)</label><div class="row2"><input name="p" type="text" minlength="8" autocomplete="off" required style="flex:1;min-width:200px"><button>Definir</button></div></form></div>'
            f'<div class="card"><h2>Estado</h2><div class="row2">{btn("admin", "Remover admin" if t["is_admin"] else "Tornar admin")}{btn("disable", "Reativar conta" if t["disabled"] else "Suspender conta", "d")}</div>'
            f'<p class="m">Uma conta suspensa não consegue entrar, mas os dados ficam guardados.</p></div>'
            f'<details><summary>Apagar conta e todos os dados</summary><form class="f" method="post" action="{base}/delete"><p class="m">Apaga a conta e os dados associados: {pl(ne, "evento")} · {pl(nc, "cliente")}. Não dá para desfazer (só com um backup). '
            f'Escreve <b>{e(t["username"])}</b> para confirmar.</p><input name="confirm" autocomplete="off" required><p><button class="d">Apagar definitivamente</button></p></form></details>'), ok, err)

    def a_site(self, u, ok=""):
        c = cfg(); ck = lambda k: "checked" if c[k] == "1" else ""
        lopts = "".join(f'<option value="{k}"{" selected" if cfg()["lang"] == k else ""}>{v}</option>' for k, v in i18n.LANGS.items())
        presets = [("Azul", "#3b4cdb,#e5484d,#f0a020,#2fa56b"), ("Esmeralda", "#0f766e,#e5484d,#f0a020,#2fa56b"), ("Violeta", "#7c3aed,#e11d48,#f59e0b,#16a34a"),
                   ("Laranja", "#ea580c,#dc2626,#ca8a04,#15803d"), ("Grafite", "#334155,#e5484d,#f0a020,#2fa56b")]
        pb = "".join(f'<button type="button" data-c="{v}">{n}</button>' for n, v in presets)
        cin = lambda k, lab: f'<div><label>{lab}</label><input type="color" id="{k}" name="{k}" value="{c[k]}"></div>'
        lg = logo(c).replace('class="lg"', 'class="lg" id="pvlogo"')
        return self.apage(u, "/admin/site", (
            '<form class="f card" method="post" action="/admin/site/texts"><h2>Nomes e textos</h2>' + fld("Nome do site", "site_name", val=c["site_name"], extra='maxlength="40" required')
            + fld("Título da página de entrada", "hero_title", val=c["hero_title"], extra='maxlength="140"') + f'<label>Texto da página de entrada</label><textarea name="hero_text" rows="3" maxlength="300">{e(c["hero_text"])}</textarea>'
            f'<label>Idioma por defeito</label><select name="lang">{lopts}</select><p class="m">Usado quando o browser do visitante não indica um idioma disponível.</p>'
            f'<label class="c" style="margin-top:16px"><input type="checkbox" name="reg_open" {ck("reg_open")}>Permitir que novas pessoas criem conta</label>'
            + fld("Código de convite (vazio = sem código)", "invite", val=c["invite"], extra='maxlength="60" autocomplete="off"') + '<p><button class="p">Guardar</button></p></form>'
            '<form class="f card" method="post" action="/admin/site/colors"><h2>Cores</h2><p class="m">Mudam em todo o site e no ícone do separador. O modo escuro ajusta-se sozinho.</p>'
            f'<div class="pre">{pb}</div><div class="g4">{cin("c_brand", "Principal")}{cin("c_todo", "Por faturar")}{cin("c_inv", "Faturada")}{cin("c_paid", "Paga")}</div>'
            f'<div id="pv" class="card" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:16px 0 0;--brand:{c["c_brand"]};--todo:{c["c_todo"]};--inv:{c["c_inv"]};--paid:{c["c_paid"]}">{lg}'
            '<button type="button" class="p">Botão</button><span class="chip on f">✓ Faturada</span><span class="chip on p2">✓ Paga</span><b style="color:var(--todo)">Por faturar</b></div>'
            '<p class="row2" style="margin-top:14px"><button class="p">Guardar cores</button><button type="submit" formaction="/admin/site/reset" formnovalidate>Repor cores originais</button></p></form>'
            '<script nonce="__NONCE__">(function(){var ids=["c_brand","c_todo","c_inv","c_paid"],nm=["brand","todo","inv","paid"],pv=document.getElementById("pv"),lr=document.querySelectorAll("#pvlogo rect");'
            'function upd(){ids.forEach(function(k,i){var v=document.getElementById(k).value;pv.style.setProperty("--"+nm[i],v);lr[i].setAttribute("fill",v)})}'
            'ids.forEach(function(k){document.getElementById(k).oninput=upd});document.querySelectorAll("[data-c]").forEach(function(b){b.onclick=function(){var v=b.dataset.c.split(",");ids.forEach(function(k,i){document.getElementById(k).value=v[i]});upd()}});upd()})();</script>'), ok)

    def a_ads(self, u, ok=""):
        c = cfg(); ck = lambda k: "checked" if c[k] == "1" else ""
        prev = ad_html(dict(c, ad_on="1", ad_app="1"), "app") or '<p class="m">Preenche uma imagem ou um texto para ver a pré-visualização.</p>'
        return self.apage(u, "/admin/ads", (
            '<form class="f card" method="post" action="/admin/ads/save"><h2>Banner de publicidade</h2><p class="m">Aparece como um banner com a indicação «Publicidade». Aceita imagem ou texto, com ligação opcional. '
            'Scripts de anúncios (por exemplo AdSense) ficam bloqueados por segurança.</p>'
            f'<label class="c"><input type="checkbox" name="ad_on" {ck("ad_on")}>Mostrar publicidade</label>'
            + fld("URL da imagem (https://...)", "ad_img", "url", c["ad_img"], 'placeholder="https://..."') + fld("Ligação ao clicar (opcional)", "ad_link", "url", c["ad_link"], 'placeholder="https://..."')
            + fld("Texto (usa-se também como descrição da imagem)", "ad_text", val=c["ad_text"], extra='maxlength="120"')
            + f'<label>Onde aparece</label><label class="c"><input type="checkbox" name="ad_app" {ck("ad_app")}>Dentro da aplicação (topo de cada página)</label>'
            f'<label class="c"><input type="checkbox" name="ad_auth" {ck("ad_auth")}>Páginas de entrada e registo</label><p><button class="p">Guardar</button></p></form>'
            f'<h2>Pré-visualização</h2><div style="max-width:720px">{prev}</div>'), ok)

    def a_db(self, u, ok="", t="", q="", res=None, err=""):
        tabs = [r["name"] for r in rows("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        cnt = {x: one('select count(*) from "' + x + '"')[0] for x in tabs}
        chips = "".join(f'<a href="/admin/db?t={x}#sql">{x} ({cnt[x]})</a>' for x in tabs)
        if res is None and t in tabs:
            q = f'select * from "{t}" limit 100'; res = sql_run(q, False)
        cols, data, info = res if res else (None, None, "")
        bks = "".join(f'<div class="bk"><span><b>{fn[9:13]}-{fn[13:15]}-{fn[15:17]} {fn[18:20]}:{fn[20:22]}</b> <span class="m">· {fn.rsplit("-", 1)[1][:-3]} · {fsize(sz)}</span></span><a class="btn" href="/admin/backups/{fn}">Descarregar</a></div>' for fn, sz in list_backups()[:15]) \
            or '<p class="m">Ainda não há backups guardados no servidor.</p>'
        return self.apage(u, "/admin/db", (
            f'<div class="card"><h2>Backups</h2><p class="m">Há um backup automático por dia (guarda os últimos 14). Ficam na pasta de dados do servidor, por isso descarrega de vez em quando uma cópia para outro sítio.</p>'
            f'<div class="row2"><a class="btn p" href="/admin/backup.db">Criar e descarregar backup agora</a><form method="post" action="/admin/db/snapshot"><button>Criar backup no servidor</button></form></div><div style="margin-top:12px">{bks}</div></div>'
            '<form class="f card" id="rf"><h2>Restaurar um backup</h2><p class="m">Substitui <b>toda</b> a base de dados atual pelo ficheiro escolhido (um .db descarregado daqui). É criado um backup do estado atual antes. Depois tens de entrar de novo.</p>'
            '<input type="file" id="rfile" accept=".db,.sqlite,application/octet-stream" required><p><button class="d" id="rb">Restaurar</button></p></form>'
            f'<div class="card" id="sql"><h2>Ver e editar dados</h2><p class="m">Tabelas (clica para ver as primeiras 100 linhas):</p><div class="chips">{chips}</div>'
            f'<form class="f" method="post" action="/admin/db/sql#sql"><textarea name="q" rows="4" class="mono" spellcheck="false">{e(q or "select id, username, email from users")}</textarea>'
            '<label class="c" style="margin-top:10px"><input type="checkbox" name="confirm">Confirmo que esta instrução pode alterar dados (é criado um backup antes)</label>'
            '<p class="m">Exemplos: <code>' + e("update users set email='novo@exemplo.pt' where id=2") + '</code> · <code>' + e("update events set user_id=3 where id=10") + '</code></p><p><button class="p">Executar</button></p></form>'
            + (f'<p class="msg {"err" if info.startswith(("Erro", "Esta")) else "ok"}">{e(info)}</p>' if info else "") + sql_table(cols, data or []) + '</div>'
            '<script nonce="__NONCE__">document.getElementById("rf").onsubmit=function(ev){ev.preventDefault();var f=document.getElementById("rfile").files[0],b=document.getElementById("rb");if(!f)return;'
            'if(!confirm("' + tx("Isto substitui TODA a base de dados atual pela do ficheiro. Continuar?") + '"))return;b.disabled=true;b.textContent="' + tx("A restaurar...") + '";'
            'fetch("/admin/db/restore",{method:"POST",body:f,headers:{"Content-Type":"application/octet-stream"}}).then(function(r){return r.text().then(function(t){if(r.ok){location.href="/login"}else{alert(t);b.disabled=false;b.textContent="' + tx("Restaurar") + '"}})})'
            '.catch(function(){alert("' + tx("Falhou o envio do ficheiro.") + '");b.disabled=false;b.textContent="' + tx("Restaurar") + '"})};</script>'), ok, err)

    def admin_post(self, u, p, parts, f):
        if not u["is_admin"]: return self.out(page("Não encontrado", "<h1>Página não encontrada</h1>", "", u), 404)
        yes = lambda k: "1" if f.get(k) else "0"
        if p == "/admin/site/texts":
            set_cfg({"site_name": f.get("site_name", "").strip()[:40] or DEFAULTS["site_name"], "hero_title": f.get("hero_title", "").strip()[:140] or DEFAULTS["hero_title"],
                     "hero_text": f.get("hero_text", "").strip()[:300] or DEFAULTS["hero_text"], "reg_open": yes("reg_open"), "invite": f.get("invite", "").strip()[:60], "lang": f.get("lang") if f.get("lang") in i18n.LANGS else "pt"})
            return self.go("/admin/site?ok=texts")
        if p == "/admin/site/colors":
            if not all(HEX.match(f.get(k, "")) for k in COLOR_KEYS): return self.out(self.apage(u, "/admin/site", "", err="Cor inválida."), 400)
            set_cfg({k: f[k].lower() for k in COLOR_KEYS}); return self.go("/admin/site?ok=colors")
        if p == "/admin/site/reset": set_cfg({k: DEFAULTS[k] for k in COLOR_KEYS}); return self.go("/admin/site?ok=reset")
        if p == "/admin/ads/save":
            img, link = f.get("ad_img", "").strip(), f.get("ad_link", "").strip()
            set_cfg({"ad_on": yes("ad_on"), "ad_img": img if img.startswith("https://") else "", "ad_link": link if re.match(r"^https?://", link) else "",
                     "ad_text": f.get("ad_text", "").strip()[:120], "ad_app": yes("ad_app"), "ad_auth": yes("ad_auth")})
            return self.go("/admin/ads?ok=ads")
        if p == "/admin/users/promote":
            q = f.get("q", "").strip()[:120].lower()
            ts = [r for r in rows("select * from users where disabled=0 and is_admin=0") if q and (q in r["username"].lower() or q in (r["email"] or "").lower() or q in (r["name"] or "").lower())]
            ex = [r for r in ts if q in (r["username"].lower(), (r["email"] or "").lower())]
            t = ex[0] if ex else (ts[0] if len(ts) == 1 else None)
            if t: run("update users set is_admin=1 where id=?", (t["id"],)); return self.go("/admin/users?ok=newadmin")
            return self.go("/admin/users?ok=nouser")
        if p == "/admin/users/bulkdelete":
            ids = [int(x) for x in self.fl.get("ids", []) if x.isdigit() and int(x) != u["id"]]
            if not ids or not f.get("confirm"): return self.go("/admin/users?ok=nosel")
            make_backup("predelete")
            for x in ids: purge_user(x)
            return self.go("/admin/users?ok=bulkdel")
        if len(parts) == 4 and parts[1] == "support":
            t = one("select * from tickets where id=?", (parts[2],))
            if not t: return self.go("/admin/support")
            act, base = parts[3], f"/admin/support/{t['id']}"
            if act == "reply":
                body = f.get("body", "").strip()[:3000]
                if not body: return self.out(self.a_ticket(u, t["id"], err="Escreve a resposta."), 400)
                now = now_str(); run("insert into tmsgs(ticket_id,from_admin,body,created) values(?,?,?,?)", (t["id"], 1, body, now))
                run("update tickets set updated=?, unread_user=1, unread_admin=0 where id=?", (now, t["id"]))
                if smtp_ready() and BASE_URL:
                    mail_async(t["email"], i18n.mail("reply_s", t["lang"], site=SN()), i18n.mail("reply_b", t["lang"], name=t["name"], subject=t["subject"], reply=body, url=f"{BASE_URL}/support/t/{t['token']}"))
                return self.go(base + "?ok=reply")
            if act == "close":
                run("update tickets set status=? where id=?", ("open" if t["status"] == "closed" else "closed", t["id"]))
                return self.go(("/admin/support" if t["status"] != "closed" else base) + ("?ok=closed" if t["status"] != "closed" else "?ok=reopened"))
            if act == "delete": run("delete from tickets where id=?", (t["id"],)); return self.go("/admin/support?ok=deleted")
        if p == "/admin/db/snapshot": make_backup("manual"); return self.go("/admin/db?ok=snap")
        if p == "/admin/db/sql":
            q = f.get("q", "").strip()
            if not q: return self.go("/admin/db")
            res = sql_run(q, bool(f.get("confirm")))
            return self.out(self.a_db(u, q=q, res=res))
        if len(parts) == 4 and parts[1] == "user":
            t = one("select * from users where id=?", (parts[2],))
            if not t: return self.go("/admin/users")
            tid, act = t["id"], parts[3]; me = tid == u["id"]; back = f"/admin/user/{tid}"
            bad = lambda m: self.out(self.a_user(u, tid, err=m), 400)
            if act == "save":
                un, name, em, ph = f.get("username", "").strip(), f.get("name", "").strip()[:60], f.get("email", "").strip(), f.get("phone", "").strip()[:30]
                if not re.match(r"^[\w.\-]{3,30}$", un) or not name or not re.match(EMAIL_RE, em): return bad("Utilizador (3 a 30 caracteres), nome e email têm de ser válidos.")
                try: run("update users set username=?, name=?, email=?, phone=? where id=?", (un, name, em, ph, tid))
                except sqlite3.IntegrityError: return bad("Esse utilizador ou email já existe noutra conta.")
                return self.go(back + "?ok=user")
            if act == "admin":
                if t["is_admin"] and (me or one("select count(*) from users where is_admin=1")[0] <= 1): return bad("Não podes remover o último administrador, nem a ti próprio.")
                run("update users set is_admin=? where id=?", (0 if t["is_admin"] else 1, tid)); return self.go(back + "?ok=state")
            if act == "disable":
                if me: return bad("Não te podes suspender a ti próprio.")
                run("update users set disabled=? where id=?", (0 if t["disabled"] else 1, tid)); return self.go(back + "?ok=state")
            if act == "password":
                if len(f.get("p", "")) < 8: return bad("A palavra-passe tem de ter pelo menos 8 caracteres.")
                run("update users set pw=? where id=?", (hash_pw(f["p"]), tid)); run("delete from resets where user_id=?", (tid,))
                return self.go(back + "?ok=pw", [session_cookie(one("select * from users where id=?", (tid,)), self.https())] if me else [])
            if act == "link":
                tok = secrets.token_urlsafe(32); run("delete from resets where user_id=? or exp<?", (tid, time.time()))
                run("insert into resets values(?,?,?)", (hashlib.sha256(tok.encode()).hexdigest(), tid, int(time.time()) + 3600))
                host = BASE_URL or ("https://" if self.https() else "http://") + str(self.headers.get("Host"))
                return self.out(self.a_user(u, tid, link=f"{host}/reset?t={tok}"))
            if act == "ics": run("update users set ics=? where id=?", (secrets.token_hex(20), tid)); return self.go(back + "?ok=ics")
            if act == "delete":
                if me: return bad("Não podes apagar a tua própria conta aqui.")
                if f.get("confirm", "").strip().lower() != t["username"].lower(): return bad("Para apagar, escreve exatamente o nome de utilizador.")
                make_backup("predelete")
                purge_user(tid)
                return self.go("/admin/users")
        self.go("/admin")

    def restore(self):
        u = self.user()
        if not (u and u["is_admin"]): return self.out("Não autorizado", 403, "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0 or n > 100_000_000: return self.out("Ficheiro inválido ou demasiado grande (máximo 100 MB).", 400, "text/plain")
        os.makedirs(BACKUP_DIR, exist_ok=True); tmp = os.path.join(BACKUP_DIR, "upload.tmp")
        try:
            left = n
            with open(tmp, "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk: break
                    fh.write(chunk); left -= len(chunk)
            with open(tmp, "rb") as fh: magic = fh.read(16)
            if magic != b"SQLite format 3\x00": return self.out("Isto não é um ficheiro de base de dados SQLite.", 400, "text/plain")
            s = sqlite3.connect(tmp)
            try:
                if s.execute("pragma integrity_check").fetchone()[0] != "ok": return self.out("O ficheiro está danificado.", 400, "text/plain")
                if not {"users", "events", "clients", "kv"} <= {r[0] for r in s.execute("select name from sqlite_master where type='table'")}:
                    return self.out("Este ficheiro não parece ser uma base de dados da Claquete.", 400, "text/plain")
                make_backup("prerestore"); d = db()
                try: s.backup(d)
                finally: d.close()
            finally: s.close()
            init(); self.out("ok", 200, "text/plain")
        except sqlite3.Error as ex: self.out(f"Erro: {ex}", 400, "text/plain")
        finally:
            if os.path.exists(tmp): os.remove(tmp)

    # ---- início
    def home(self, u, m):
        first, prev, nxt = month_nav(m); ym = first.strftime("%Y-%m"); i = u["id"]; mn = MES[first.month - 1]
        a = rows(EV + "where e.user_id=? and e.invoice_date is null order by e.start_date", (i,))
        b = rows(EV + "where e.user_id=? and e.invoice_date is not null and e.paid=0 order by e.invoice_date", (i,))
        up = rows(EV + "where e.user_id=? and e.end_date>=? order by e.start_date limit 5", (i, today().isoformat()))
        fm = one("select coalesce(sum(amount),0) s from events where user_id=? and substr(invoice_date,1,7)=?", (i,ym))["s"]
        rm = one("select coalesce(sum(amount),0) s from events where user_id=? and paid=1 and substr(invoice_date,1,7)=?", (i,ym))["s"]
        s = lambda l: sum(x["amount"] or 0 for x in l)
        tile = lambda c, lab, val, sub: f'<div class="st" style="--c:{c}"><span>{lab}</span><b>{eur(val)}</b><span>{sub}</span></div>'
        return page("Início", f'<div class="bar-h"><div><h1>Olá, {e(u["name"] or u["username"])}</h1><p class="sub" style="margin:0">O ponto da situação.</p></div><a class="btn p" href="/event/new">Novo evento</a></div>'
            f'<div class="mn"><a class="btn" href="/?m={prev}">‹</a><b>{mn} {first.year}</b><a class="btn" href="/?m={nxt}">›</a><span class="m">aplica-se a Faturado e Recebido</span></div>'
            '<div class="strip">' + tile("var(--todo)", "Por faturar", s(a), pl(len(a), "evento")) + tile("var(--inv)", "Faturado, por receber", s(b), pl(len(b), "evento"))
            + tile("var(--brand)", f"Faturado em {mn}", fm, "pela data da fatura") + tile("var(--paid)", f"Recebido de {mn}", rm, "já pago") + '</div>'
            + "<h2>Por faturar</h2>" + lst(a, "/", "Nada por faturar. 🎬") + "<h2>Por receber</h2>" + lst(b, "/", "Nada por receber.") + "<h2>Próximos eventos</h2>" + lst(up, "/", "Sem eventos futuros."), "/", u)

    # ---- eventos
    def events(self, u, f):
        w = {"faturar": "and e.invoice_date is null", "receber": "and e.invoice_date is not null and e.paid=0", "pagos": "and e.paid=1"}.get(f, "")
        r = rows(EV + f"where e.user_id=? {w} order by e.start_date desc", (u["id"],))
        chips = "".join(f'<a class="{"on" if f == k else ""}" href="/events?f={k}">{n}</a>' for k, n in [("todos", "Todos"), ("faturar", "Por faturar"), ("receber", "Por receber"), ("pagos", "Pagos")])
        return page("Eventos", f'<div class="bar-h"><h1>Eventos</h1><a class="btn p" href="/event/new">Novo evento</a></div><div class="chips">{chips}</div>' + lst(r, f"/events?f={f}", "Sem eventos."), "/events", u)

    def event_form(self, u, i, date=""):
        v = None
        if i != "new":
            v = one("select * from events where id=? and user_id=?", (i, u["id"]))
            if not v: raise ValueError
        its = [(x["label"], x["amount"]) for x in rows("select * from items where event_id=? order by id", (i,))] if v else []
        sd = v["start_date"] if v else (okdate(date) or today().isoformat()); ed = v["end_date"] if v else sd
        cl = "".join(f'<option value="{c["id"]}" data-i="{e(" · ".join(x for x in (c["rate"], c["terms"]) if x))}" {"selected" if v and c["id"] == v["client_id"] else ""}>{e(c["name"])}</option>' for c in rows("select * from clients where user_id=? order by name", (u["id"],)))
        rowsh = "".join(f'<div class="it"><input name="label" list="sug" value="{e(l)}" placeholder="Descrição"><input name="amt" inputmode="decimal" value="{f"{a:g}".replace(".", dsep())}" placeholder="0{dsep()}00"></div>' for l, a in (its or [(tx("Diária"), 0)]))
        dele = f'<details><summary>Apagar evento</summary><form method="post" action="/event/{v["id"]}/delete"><p class="m">Esta ação não pode ser desfeita.</p><button class="d">Confirmar: apagar</button></form></details>' if v else ""
        ck = lambda x: "checked" if x else ""
        return page("Evento", f'<h1>{"Editar" if v else "Novo"} evento</h1><form class="f card" method="post" action="/event/save"><input type="hidden" name="id" value="{v["id"] if v else ""}">'
            + fld("Título", "title", val=v["title"] if v else "", extra="required" + ("" if v else " autofocus"))
            + f'<div class="g2"><div><label>Data de início</label><input type="date" id="sd" name="start" value="{sd}" required></div><div><label>Data de fim</label><input type="date" id="ed" name="end" value="{ed}" required></div></div>'
            f'<label>Cliente</label><select id="cs" name="client_id"><option value="">— sem cliente —</option>{cl}</select><div class="info" id="ci" hidden></div>'
            f'<label>Valores</label><div id="items">{rowsh}</div><button type="button" id="add">+ Adicionar linha</button><div class="sum">Total<span id="tot">0{dsep()}00 €</span></div>'
            '<datalist id="sug">' + "".join(f'<option value="{eh(tx(x))}">' for x in ("Diária", "Meia diária", "Hora extra", "Aluguer de equipamento", "Deslocação", "Edição")) + '</datalist>'
            + f'<div class="g2"><div><label>Data da fatura (vazio = por faturar)</label><input type="date" name="invoice_date" value="{e(v["invoice_date"] if v else "")}"></div><div><label>N.º da fatura</label><input name="invoice_no" value="{e(v["invoice_no"] if v else "")}"></div></div>'
            f'<label class="c" style="margin-top:14px"><input type="checkbox" name="paid" {ck(v and v["paid"])}>Fatura paga (já recebi)</label><label>Notas</label><textarea name="notes" rows="3">{e(v["notes"] if v else "")}</textarea>'
            '<p><button class="p">Guardar</button> <a class="btn" href="/events">Cancelar</a></p></form>' + dele
            + '<script nonce="__NONCE__">(function(){var L=document.getElementById("items"),T=document.getElementById("tot");function tot(){var s=0;L.querySelectorAll("[name=amt]").forEach(function(i){s+=parseFloat(i.value.replace(",","."))||0});T.textContent=s.toFixed(2).replace(".","' + dsep() + '")+" €"}'
            'L.addEventListener("input",tot);tot();document.getElementById("add").onclick=function(){var d=document.createElement("div");d.className="it";d.innerHTML=\'<input name="label" list="sug" placeholder="' + tx("Descrição") + '"><input name="amt" inputmode="decimal" placeholder="0' + dsep() + '00">\';L.appendChild(d);d.firstChild.focus()};'
            'var S=document.getElementById("cs"),I=document.getElementById("ci");function inf(){var o=S.options[S.selectedIndex];I.textContent=o.dataset.i||"";I.hidden=!o.dataset.i}S.onchange=inf;inf();'
            'var a=document.getElementById("sd"),b=document.getElementById("ed");a.onchange=function(){if(!b.value||b.value<a.value)b.value=a.value}})();</script>', "/events", u)

    def save_event(self, u, f):
        i = u["id"]; ex = one("select * from events where id=? and user_id=?", (f.get("id") or 0, i))
        sd = okdate(f.get("start", "")) or today().isoformat(); ed = okdate(f.get("end", "")) or sd; ed = sd if ed < sd else ed
        cid = f.get("client_id") if one("select 1 from clients where id=? and user_id=?", (f.get("client_id") or 0, i)) else None
        its = [(l.strip()[:80], num(a)) for l, a in zip(self.fl.get("label", []), self.fl.get("amt", [])) if l.strip() or a.strip()]
        inv = okdate(f.get("invoice_date", "")); paid = 1 if f.get("paid") else 0; t = today().isoformat()
        if paid and not inv: inv = t
        if not inv: paid = 0
        pd = (ex["paid_date"] if ex and ex["paid_date"] else t) if paid else None
        v = (f.get("title", "").strip()[:150] or "Evento", sd, ed, cid, sum(a for _, a in its), inv, f.get("invoice_no", "").strip()[:40], paid, pd, f.get("notes", "")[:2000])
        c = db()
        try:
          if ex: c.execute("update events set title=?,start_date=?,end_date=?,client_id=?,amount=?,invoice_date=?,invoice_no=?,paid=?,paid_date=?,notes=? where id=?", v + (ex["id"],)); eid = ex["id"]
          else: eid = c.execute("insert into events(title,start_date,end_date,client_id,amount,invoice_date,invoice_no,paid,paid_date,notes,user_id) values(?,?,?,?,?,?,?,?,?,?,?)", v + (i,)).lastrowid
          c.execute("delete from items where event_id=?", (eid,)); c.executemany("insert into items(event_id,label,amount) values(?,?,?)", [(eid, l, a) for l, a in its]); c.commit()
        finally: c.close()
        self.go("/events")

    # ---- clientes
    def clients(self, u):
        r = rows("select c.*, (select count(*) from events where client_id=c.id) n, (select coalesce(sum(amount),0) from events where client_id=c.id and paid=0 and invoice_date is not null) due from clients c where user_id=? order by name", (u["id"],))
        l = "".join(f'<div class="er"><a class="eh" href="/client/{c["id"]}">{avatar(c["name"], c["logo"])}<div><b>{e(c["name"])}</b><small>{e(c["rate"]) if c["rate"] else "sem valores definidos"} · {pl(c["n"], "evento")}</small></div></a><span class="amt">{eur(c["due"]) if c["due"] else ""}</span></div>' for c in r)
        return page("Clientes", f'<div class="bar-h"><h1>Clientes</h1><a class="btn p" href="/client/new">Novo cliente</a></div><div class="list">{l or "<div class=empty>Ainda sem clientes.</div>"}</div>', "/clients", u)

    def client_form(self, u, i):
        v = None
        if i != "new":
            v = one("select * from clients where id=? and user_id=?", (i, u["id"]))
            if not v: raise ValueError
        g = lambda k: v[k] if v else ""
        ta = lambda k, lab: f'<label>{lab}</label><textarea name="{k}" rows="3">{e(g(k))}</textarea>'
        hist = ("<h2>Eventos deste cliente</h2>" + lst(rows(EV + "where e.user_id=? and e.client_id=? order by e.start_date desc", (u["id"], i)), f"/client/{i}", "Sem eventos.")) if v else ""
        dele = f'<details><summary>Apagar cliente</summary><form method="post" action="/client/{v["id"]}/delete"><p class="m">Os eventos ficam, mas sem cliente.</p><button class="d">Confirmar: apagar</button></form></details>' if v else ""
        return page("Cliente", f'<div class="bar-h"><h1>{"Editar" if v else "Novo"} cliente</h1>{avatar(g("name") or "?", g("logo")) if v else ""}</div><form class="f card" method="post" action="/client/save"><input type="hidden" name="id" value="{g("id")}">'
            + fld("Nome", "name", val=g("name"), extra="required") + fld("URL do logo (opcional)", "logo", "url", g("logo"), 'placeholder="https://..."') + fld("NIF", "nif", val=g("nif")) + fld("Contacto", "contact", val=g("contact"))
            + fld("Valores acordados (ex.: 250 €/dia)", "rate", val=g("rate")) + ta("terms", "Condições de pagamento") + ta("notes", "Notas") + '<p><button class="p">Guardar</button> <a class="btn" href="/clients">Cancelar</a></p></form>' + hist + dele, "/clients", u)

    # ---- calendário
    def cal(self, u, m):
        first, prev, nxt = month_nav(m); i = u["id"]; weeks = calendar.Calendar(0).monthdatescalendar(first.year, first.month)
        lo, hi = weeks[0][0].isoformat(), weeks[-1][-1].isoformat()
        evs = rows(EV + "where e.user_id=? and e.start_date<=? and e.end_date>=? order by e.start_date, e.end_date desc", (i, hi, lo)); out = ""
        for wk in weeks:
            w0, w1 = wk[0].isoformat(), wk[6].isoformat(); lanes = []; bars = ""
            for r in [r for r in evs if r["start_date"] <= w1 and r["end_date"] >= w0]:
                s = max(0, (D(r["start_date"]) - wk[0]).days); en = min(6, (D(r["end_date"]) - wk[0]).days)
                for li, last in enumerate(lanes):
                    if s > last: lanes[li] = en; lane = li; break
                else: lanes.append(en); lane = len(lanes) - 1
                cls = state(r) + (" cs" if r["start_date"] >= w0 else "") + (" ce" if r["end_date"] <= w1 else "")
                bars += f'<a class="bar {cls}" style="grid-column:{s + 1}/{en + 2};grid-row:{lane + 2}" href="/event/{r["id"]}" title="{e(r["title"])} · {e(r["cn"] or "")} · {eur(r["amount"])}">{e(r["title"])}</a>'
            L = len(lanes)
            cells = "".join(f'<a class="cell{" c0" if k == 0 else ""}{" out" if d.month != first.month else ""}{" we" if k > 4 else ""}{" now" if d == today() else ""}" style="grid-column:{k + 1};grid-row:1/span {L + 2}" href="/event/new?date={d.isoformat()}"><span>{d.day}</span></a>' for k, d in enumerate(wk))
            out += f'<div class="wk" style="grid-template-rows:30px repeat({L},var(--lh)) minmax(8px,1fr)">{cells}{bars}</div>'
        fm, lm = first.isoformat(), ((first + dt.timedelta(32)).replace(day=1) - dt.timedelta(1)).isoformat()
        month_ev = rows(EV + "where e.user_id=? and e.start_date<=? and e.end_date>=? order by e.start_date", (i, lm, fm))
        return page("Calendário", f'<div class="bar-h"><div class="mn" style="margin:0"><a class="btn" href="/calendar?m={prev}">‹</a><b style="font-size:1.3rem">{MES[first.month - 1]} {first.year}</b><a class="btn" href="/calendar?m={nxt}">›</a><a class="btn" href="/calendar">Hoje</a></div><a class="btn p" href="/event/new">Novo evento</a></div>'
            '<div class="cal"><div class="dh">' + "".join(f"<div>{d}</div>" for d in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")) + f'</div>{out}</div>'
            '<div class="lgd m"><span style="--c:var(--todo)">por faturar</span><span style="--c:var(--inv)">faturada</span><span style="--c:var(--paid)">paga</span><span>toca num dia para criar um evento</span></div>'
            + "<h2>Neste mês</h2>" + lst(month_ev, f"/calendar?m={first:%Y-%m}", "Sem eventos neste mês."), "/calendar", u)

    def ics(self, k):
        u = one("select * from users where ics=?", (k,)) if k else None
        if not u: return self.out("Não autorizado", 403, "text/plain")
        esc = lambda s: str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
        L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Claquete//PT", f"X-WR-CALNAME:{SN()}"]
        for r in rows(EV + "where e.user_id=? order by e.start_date", (u["id"],)):
            st = "paga" if r["paid"] else "faturada" if r["invoice_date"] else "por faturar"
            L += ["BEGIN:VEVENT", f"UID:ev{r['id']}@claquete", f"DTSTAMP:{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}", f"DTSTART;VALUE=DATE:{r['start_date'].replace('-', '')}",
                  f"DTEND;VALUE=DATE:{(D(r['end_date']) + dt.timedelta(1)):%Y%m%d}", f"SUMMARY:{esc(r['title'])}", f"DESCRIPTION:{esc((r['cn'] or '') + ' | ' + eur(r['amount']) + ' | ' + st)}", "END:VEVENT"]
        self.out("\r\n".join(L + ["END:VCALENDAR"]) + "\r\n", 200, "text/calendar; charset=utf-8")

    # ---- estatísticas
    def stats(self, u, y):
        i = u["id"]; cur = today().year
        years = sorted({int(r["y"]) for r in rows("select distinct substr(invoice_date,1,4) y from events where user_id=? and invoice_date is not null", (i,))} | {cur}, reverse=True)
        try: y = int(y)
        except ValueError: y = cur
        fat, rec, cnt = [0.0] * 12, [0.0] * 12, [0] * 12
        for r in rows("select cast(substr(invoice_date,6,2) as int) mo, sum(amount) f, sum(case when paid=1 then amount else 0 end) p, count(*) n from events where user_id=? and substr(invoice_date,1,4)=? group by mo", (i, str(y))):
            fat[r["mo"] - 1], rec[r["mo"] - 1], cnt[r["mo"] - 1] = r["f"] or 0, r["p"] or 0, r["n"]
        cl = rows("select coalesce(c.name,'Sem cliente') name, c.logo, count(*) n, sum(e.amount) v, sum(julianday(e.end_date)-julianday(e.start_date)+1) d from events e left join clients c on c.id=e.client_id where e.user_id=? and substr(e.invoice_date,1,4)=? group by e.client_id order by v desc", (i, str(y)))
        tf, tr, td = sum(fat), sum(rec), sum(c["d"] for c in cl); act = [k for k in range(12) if fat[k] > 0]
        best = max(act, key=lambda k: fat[k]) if act else None; worst = min(act, key=lambda k: fat[k]) if len(act) > 1 else None
        chips = "".join(f'<a class="{"on" if x == y else ""}" href="/stats?y={x}">{x}</a>' for x in years)
        tile = lambda c, lab, val, sub="": f'<div class="st" style="--c:{c}"><span>{lab}</span><b>{val}</b><span>{sub}</span></div>'
        strip = '<div class="strip">' + tile("var(--brand)", "Faturado", eur(tf), f"média {eur(tf / len(act)) if act else '—'}/mês") + tile("var(--paid)", "Recebido", eur(tr), f"por receber {eur(tf - tr)}") \
            + tile("var(--inv)", "Dias trabalhados", f"{td:g}", pl(sum(cnt), "evento")) + tile("var(--todo)", "Melhor mês", MES[best].capitalize() if best is not None else "—", eur(fat[best]) if best is not None else "") + '</div>'
        mt = "".join(f'<tr class="{"best" if k == best else "worst" if k == worst else ""}"><td>{MES[k].capitalize()}</td><td>{cnt[k]}</td><td>{eur(fat[k])}</td><td>{eur(rec[k])}</td><td>{eur(fat[k] - rec[k])}</td></tr>' for k in range(12))
        mx = max([c["v"] or 0 for c in cl] + [1]); mxd = max([c["d"] or 0 for c in cl] + [1])
        hb = lambda key, mxv, fmt: "".join(f'<div class="hb"><span>{e(c["name"])}</span><div class="t"><i style="width:{max(2, 100 * (c[key] or 0) / mxv):.0f}%"></i></div><b>{fmt(c[key])}</b></div>' for c in cl[:8]) or '<p class="m">Sem dados neste ano.</p>'
        ct = "".join(f'<tr><td>{e(c["name"])}</td><td>{c["n"]}</td><td>{c["d"]:g}</td><td>{eur(c["v"])}</td><td>{eur(c["v"] / c["d"]) if c["d"] else "—"}</td><td>{100 * c["v"] / tf:.0f}%</td></tr>' for c in cl) if tf else ""
        return page("Estatísticas", f'<div class="bar-h"><div><h1>Estatísticas</h1><p class="sub" style="margin:0">Contam os eventos já faturados, no mês e ano da data da fatura.</p></div></div><div class="chips">{chips}</div>{strip}'
            f'<h2>Faturado e recebido por mês</h2><div class="card">{self.chart(fat, rec)}<div class="lgd m"><span style="--c:var(--brand)">faturado</span><span style="--c:var(--paid)">recebido</span></div></div>'
            f'<div class="card sc"><table class="tb"><tr><th>Mês</th><th>Eventos</th><th>Faturado</th><th>Recebido</th><th>Por receber</th></tr>{mt}<tr><td><b>Total</b></td><td><b>{sum(cnt)}</b></td><td><b>{eur(tf)}</b></td><td><b>{eur(tr)}</b></td><td><b>{eur(tf - tr)}</b></td></tr></table></div>'
            f'<h2>Clientes</h2><div class="g2"><div class="card"><b>Quem dá mais volume</b><div style="margin-top:8px">{hb("v", mx, eur)}</div></div><div class="card"><b>Dias trabalhados</b><div style="margin-top:8px">{hb("d", mxd, lambda v: f"{v:g} dias")}</div></div></div>'
            f'<div class="card sc"><table class="tb"><tr><th>Cliente</th><th>Eventos</th><th>Dias</th><th>Faturado</th><th>€/dia</th><th>Peso</th></tr>{ct}</table></div>', "/stats", u)

    def chart(self, fat, rec):
        W, H, L, B, T = 720, 250, 46, 26, 10; pw, ph = W - L - 6, H - B - T; mv = max(fat + rec + [0])
        mag = 10 ** math.floor(math.log10(mv)) if mv > 0 else 1; mx = next((m * mag for m in (1, 2, 2.5, 5, 10) if mv <= m * mag), 10 * mag) if mv > 0 else 100
        o = f'<svg class="ch" viewBox="0 0 {W} {H}" role="img" aria-label="Faturado e recebido por mês">'
        for k in range(5): y = T + ph - ph * k / 4; o += f'<line class="gl" x1="{L}" x2="{W - 6}" y1="{y:.1f}" y2="{y:.1f}"/><text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{short(mx * k / 4)}</text>'
        sl = pw / 12
        for k in range(12):
            for j, (arr, c) in enumerate(((fat, "b1"), (rec, "b2"))):
                h = ph * arr[k] / mx; bw = sl * .32
                o += f'<rect class="{c}" x="{L + k * sl + sl * .17 + j * (bw + 2):.1f}" y="{T + ph - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3"><title>{MES[k]}: {eur(arr[k])}</title></rect>'
            o += f'<text x="{L + k * sl + sl / 2:.1f}" y="{H - 7}" text-anchor="middle">{MES[k][:3]}</text>'
        return o + "</svg>"

    # ---- chat
    CHM = {"sent": "Pedido de amizade enviado.", "already": "Já são amigos.", "pend": "Já enviaste um pedido a esta pessoa.", "accepted": "Agora são amigos.",
           "nouser": "Não encontrámos ninguém com esse utilizador ou email.", "self": "Não podes adicionar-te a ti próprio.", "limit": "Demasiados pedidos. Tenta mais tarde.",
           "reqgone": "Pedido removido.", "fgone": "Amigo removido.", "gnew": "Grupo criado.", "noname": "Dá um nome ao grupo.", "madd": "Membro adicionado.",
           "left": "Saíste do grupo.", "gdel": "Grupo apagado.", "kick": "Membro removido."}
    CHERR = ("nouser", "self", "limit", "noname")

    def chat_get(self, u, p, parts, g):
        if p == "/chat": return self.out(self.chat_home(u, g("ok")))
        cid = int(parts[1]); me = u["id"]; m = chat_member(cid, me)
        if not m: raise ValueError
        if len(parts) == 3 and parts[2] == "poll":
            after = int(g("after", "0") or 0)
            ms = rows("select m.*, u.name, u.username from chat_msgs m join users u on u.id=m.user_id where m.chat_id=? and m.id>? order by m.id limit 100", (cid, after))
            mx = one("select coalesce(max(id),0) from chat_msgs where chat_id=?", (cid,))[0]
            if mx > (m["last_read"] or 0): run("update chat_members set last_read=? where chat_id=? and user_id=?", (mx, cid, me))
            return self.out(json.dumps({"m": [{"id": x["id"], "me": x["user_id"] == me, "n": uname(x), "t": x["created"], "b": x["body"]} for x in ms]}), 200, "application/json")
        return self.out(self.chat_room(u, cid, g("ok")))

    def chat_home(self, u, k=""):
        me = u["id"]; fl = f'<p class="msg {"err" if k in self.CHERR else "ok"}">{eh(self.CHM[k])}</p>' if k in self.CHM else ""
        cs = rows("select c.*, (select max(id) from chat_msgs where chat_id=c.id) lastid, m.last_read from chats c join chat_members m on m.chat_id=c.id and m.user_id=? order by coalesce(lastid,0) desc, c.id desc", (me,))
        def crow(c):
            if c["kind"] == "dm":
                o = one("select u.* from chat_members m join users u on u.id=m.user_id where m.chat_id=? and m.user_id!=?", (c["id"], me)); title = uname(o); bd = ""
            else: title, bd = c["name"], ' <span class="bd">Grupo</span>'
            last = one("select m.body, m.user_id, u.name, u.username from chat_msgs m join users u on u.id=m.user_id where m.chat_id=? order by m.id desc limit 1", (c["id"],))
            nu = one("select count(*) from chat_msgs where chat_id=? and id>? and user_id!=?", (c["id"], c["last_read"] or 0, me))[0]
            prev = e((((uname(last) + ": ") if c["kind"] == "group" and last["user_id"] != me else "") + last["body"])[:70]) if last else "Sem mensagens."
            return (f'<div class="er {"todo" if nu else ""}"><a class="eh" href="/chat/{c["id"]}">{avatar(title, "")}<div><b>{e(title)}</b>{bd}<small>{prev}</small></div></a>'
                    f'{f"<i class=nb>{nu}</i>" if nu else ""}</div>')
        convs = "".join(crow(c) for c in cs) or '<div class="empty">Ainda não tens conversas. Adiciona um amigo para começar.</div>'
        fr = friends_of(me)
        pin = rows("select f.id fid, u.* from friends f join users u on u.id=f.a where f.b=? and f.status='pending' order by f.id", (me,))
        pout = rows("select f.id fid, u.* from friends f join users u on u.id=f.b where f.a=? and f.status='pending' order by f.id", (me,))
        who = lambda r: f'<div class="eh">{avatar(uname(r), "")}<div><b>{e(uname(r))}</b><small>@{e(r["username"])}</small></div></div>'
        btn = lambda url, label, cls="": f'<form method="post" action="{url}"><button class="{cls}">{label}</button></form>'
        reqin = ("<h2>Pedidos recebidos</h2><div class=\"list\">" + "".join(f'<div class="er">{who(r)}<div class="row2">{btn("/chat/friend/accept/" + str(r["fid"]), "Aceitar", "p")}{btn("/chat/friend/remove/" + str(r["fid"]), "Recusar")}</div></div>' for r in pin) + "</div>") if pin else ""
        reqout = ("<h2>Pedidos enviados</h2><div class=\"list\">" + "".join(f'<div class="er">{who(r)}{btn("/chat/friend/remove/" + str(r["fid"]), "Cancelar pedido")}</div>' for r in pout) + "</div>") if pout else ""
        frows = ""
        for r in fr:
            f_ = one("select id from friends where status='ok' and ((a=? and b=?) or (a=? and b=?))", (me, r["id"], r["id"], me))
            frows += f'<div class="er">{who(r)}<div class="row2">{btn("/chat/dm/" + str(r["id"]), "Mensagem", "p")}{btn("/chat/friend/remove/" + str(f_["id"]), "Remover")}</div></div>'
        friends = f'<div class="list">{frows or "<div class=empty>Ainda não tens amigos.</div>"}</div>'
        grp = ('<form class="f card" method="post" action="/chat/group/new"><h2>Novo grupo</h2>' + fld("Nome do grupo", "name", extra='maxlength="40" required')
               + '<label>Escolhe os amigos para o grupo:</label>' + "".join(f'<label class="c"><input type="checkbox" name="m" value="{r["id"]}">{e(uname(r))} <span class="m">@{e(r["username"])}</span></label>' for r in fr)
               + '<p><button class="p">Criar grupo</button></p></form>') if fr else '<div class="card"><h2 style="margin-top:0">Novo grupo</h2><p class="m" style="margin:0">Precisas de amigos para criar um grupo.</p></div>'
        add = ('<form class="f card" method="post" action="/chat/friend/add" style="margin-top:18px"><h2>Adicionar amigo</h2><div class="row2"><input name="q" maxlength="120" required autocomplete="off" placeholder="Utilizador ou email do teu amigo">'
               '<button class="p">Enviar pedido</button></div></form>')
        return page("Chat", f'<h1>Chat</h1>{fl}<h2 style="margin-top:8px">Conversas</h2><div class="list">{convs}</div>{reqin}<h2>Amigos</h2>{friends}{reqout}{add}{grp}', "/chat", u)

    def chat_room(self, u, cid, k=""):
        me = u["id"]; c = one("select * from chats where id=?", (cid,)); fl = f'<p class="msg {"err" if k in self.CHERR else "ok"}">{eh(self.CHM[k])}</p>' if k in self.CHM else ""
        mem = rows("select u.*, 1 x from chat_members m join users u on u.id=m.user_id where m.chat_id=? order by lower(coalesce(nullif(u.name,''),u.username))", (cid,))
        ms = rows("select m.*, u.name, u.username from chat_msgs m join users u on u.id=m.user_id where m.chat_id=? order by m.id desc limit 80", (cid,))[::-1]
        mx = ms[-1]["id"] if ms else 0
        run("update chat_members set last_read=(select coalesce(max(id),0) from chat_msgs where chat_id=?) where chat_id=? and user_id=?", (cid, cid, me))
        grp = c["kind"] == "group"; owner = c["owner"] == me
        if grp: title = e(c["name"])
        else:
            o = [x for x in mem if x["id"] != me]; title = e(uname(o[0]) if o else "?")
        bub = "".join(f'<div class="mg{" a" if x["user_id"] == me else ""}"><small>{"" if x["user_id"] == me else e(uname(x)) + " · "}{e(x["created"])}</small>{e(x["body"])}</div>' for x in ms)
        side = ""
        if grp:
            base = f"/chat/{cid}"
            names = ", ".join(f'{e(uname(x))}{" (Dono)" if x["id"] == c["owner"] else ""}' for x in mem)
            kick = ""
            if owner:
                inids = {x["id"] for x in mem}; cand = [x for x in friends_of(me) if x["id"] not in inids]
                addf = (f'<form method="post" action="{base}/add" class="row2"><select name="uid" style="flex:1;min-width:180px;width:auto" required><option value="">— escolhe um amigo —</option>'
                        + "".join(f'<option value="{x["id"]}">{e(uname(x))}</option>' for x in cand) + '</select><button>Adicionar</button></form>') if cand else '<p class="m">Todos os teus amigos já estão neste grupo.</p>'
                kick = "".join(f'<form method="post" action="{base}/kick/{x["id"]}" style="display:inline"><button class="d" style="padding:3px 10px;margin:2px">✕ {e(uname(x))}</button></form>' for x in mem if x["id"] != me)
                side = f'<details><summary>Adicionar ao grupo</summary><div class="card">{addf}<p>{kick}</p></div></details>'
            side += (f'<div class="row2" style="margin-top:10px"><form method="post" action="{base}/leave"><button>Sair do grupo</button></form>'
                     + (f'<form method="post" action="{base}/delete"><button class="d">Apagar grupo</button></form>' if owner else "") + "</div>")
        sub = f'<p class="sub" style="margin:0">Membros: {names}</p>' if grp else ""
        return page("Chat", f'<p><a class="m" href="/chat">‹ Chat</a></p><h1 style="margin-bottom:2px">{title}</h1>{sub}{fl}'
            f'<div class="chatbox" id="msgs" data-last="{mx}"><div class="msgs" id="ml">{bub or ""}</div></div>'
            f'<form class="row2" id="sf" method="post" action="/chat/{cid}/send"><input name="body" maxlength="1000" autocomplete="off" required placeholder="Escreve uma mensagem..."><button class="p">Enviar</button></form>{side}'
            '<script nonce="__NONCE__">(function(){var B=document.getElementById("msgs"),M=document.getElementById("ml"),F=document.getElementById("sf"),I=F.elements.body,last=+B.dataset.last,busy=0;'
            'function add(x){var d=document.createElement("div");d.className="mg"+(x.me?" a":"");var s=document.createElement("small");s.textContent=(x.me?"":x.n+" \\u00b7 ")+x.t;d.appendChild(s);d.appendChild(document.createTextNode(x.b));M.appendChild(d);if(x.id>last)last=x.id}'
            'function poll(){if(busy)return;busy=1;fetch("/chat/' + str(cid) + '/poll?after="+last,{credentials:"same-origin"}).then(function(r){return r.json()}).then(function(j){var at=B.scrollHeight-B.scrollTop-B.clientHeight<90;j.m.forEach(add);if(j.m.length&&at)B.scrollTop=B.scrollHeight;busy=0}).catch(function(){busy=0})}'
            'F.onsubmit=function(ev){ev.preventDefault();var b=I.value.trim();if(!b)return;I.value="";fetch(F.action,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:"ajax=1&body="+encodeURIComponent(b)}).then(function(){busy=0;poll();setTimeout(function(){B.scrollTop=B.scrollHeight},250)})};'
            'B.scrollTop=B.scrollHeight;setInterval(poll,3500);I.focus()})();</script>', "/chat", u)

    def chat_post(self, u, p, parts, f):
        me = u["id"]; go = lambda k="", to="/chat": self.go(to + (f"?ok={k}" if k else ""))
        if p == "/chat/friend/add":
            ip = "fr" + str(me); n, t0 = self.fails.get(ip, (0, 0))
            if n >= 20 and time.time() - t0 < 3600: return go("limit")
            self.fails[ip] = (n + 1 if time.time() - t0 < 3600 else 1, time.time())
            q = f.get("q", "").strip()[:120]; t = one("select * from users where (lower(username)=lower(?) or lower(email)=lower(?)) and disabled=0", (q, q)) if q else None
            if not t: return go("nouser")
            if t["id"] == me: return go("self")
            ex = one("select * from friends where (a=? and b=?) or (a=? and b=?)", (me, t["id"], t["id"], me))
            if ex:
                if ex["status"] == "ok": return go("already")
                if ex["a"] == me: return go("pend")
                run("update friends set status='ok' where id=?", (ex["id"],)); dm_chat(me, t["id"]); return go("accepted")
            run("insert into friends(a,b,status,created) values(?,?,'pending',?)", (me, t["id"], now_str())); return go("sent")
        if len(parts) == 4 and parts[1] == "friend" and parts[3].isdigit():
            r = one("select * from friends where id=? and (a=? or b=?)", (parts[3], me, me))
            if not r: return go()
            if parts[2] == "accept" and r["b"] == me and r["status"] == "pending":
                run("update friends set status='ok' where id=?", (r["id"],)); dm_chat(r["a"], r["b"]); return go("accepted")
            if parts[2] == "remove":
                run("delete from friends where id=?", (r["id"],))
                if r["status"] == "ok": run("delete from chats where kind='dm' and id=?", (dm_chat(r["a"], r["b"]),))
                return go("fgone" if r["status"] == "ok" else "reqgone")
            return go()
        if len(parts) == 3 and parts[1] == "dm" and parts[2].isdigit():
            if not any(x["id"] == int(parts[2]) for x in friends_of(me)): return go()
            return self.go(f"/chat/{dm_chat(me, int(parts[2]))}")
        if p == "/chat/group/new":
            name = f.get("name", "").strip()[:40]
            if not name: return go("noname")
            fids = {x["id"] for x in friends_of(me)}; sel = [int(x) for x in self.fl.get("m", []) if x.isdigit() and int(x) in fids][:49]
            cid = run("insert into chats(kind,name,owner,created) values('group',?,?,?)", (name, me, now_str()))
            for x in [me] + sel: run("insert into chat_members(chat_id,user_id) values(?,?)", (cid, x))
            return self.go(f"/chat/{cid}?ok=gnew")
        if len(parts) >= 3 and parts[1].isdigit():
            cid = int(parts[1]); c = one("select * from chats where id=?", (cid,)); act = parts[2]
            if not c or not chat_member(cid, me): raise ValueError
            room = f"/chat/{cid}"
            if act == "send":
                ip = "c" + str(me); n, t0 = self.fails.get(ip, (0, 0)); body = f.get("body", "").strip()[:1000]
                self.fails[ip] = (n + 1 if time.time() - t0 < 60 else 1, time.time())
                if body and not (n >= 40 and time.time() - t0 < 60):
                    mid = run("insert into chat_msgs(chat_id,user_id,body,created) values(?,?,?,?)", (cid, me, body, now_str()))
                    run("update chat_members set last_read=? where chat_id=? and user_id=?", (mid, cid, me))
                return self.out("ok", 200, "text/plain") if f.get("ajax") else self.go(room)
            if c["kind"] != "group": return self.go(room)
            if act == "leave":
                run("delete from chat_members where chat_id=? and user_id=?", (cid, me))
                nx = one("select user_id from chat_members where chat_id=? order by rowid limit 1", (cid,))
                if not nx: run("delete from chats where id=?", (cid,))
                elif c["owner"] == me: run("update chats set owner=? where id=?", (nx["user_id"], cid))
                return go("left")
            if c["owner"] != me: return self.go(room)
            if act == "delete": run("delete from chats where id=?", (cid,)); return go("gdel")
            if act == "add" and f.get("uid", "").isdigit() and int(f["uid"]) in {x["id"] for x in friends_of(me)}:
                run("insert or ignore into chat_members(chat_id,user_id) values(?,?)", (cid, int(f["uid"]))); return self.go(room + "?ok=madd")
            if act == "kick" and len(parts) == 4 and parts[3].isdigit() and int(parts[3]) != me:
                run("delete from chat_members where chat_id=? and user_id=?", (cid, int(parts[3]))); return self.go(room + "?ok=kick")
            return self.go(room)
        self.go("/chat")

    # ---- sobre e suporte (público)
    def about(self, u):
        c = cfg(); sn = e(c["site_name"])
        li = "".join(f"<li>{eh(x)}</li>" for x in ("Organizar eventos, incluindo trabalhos de vários dias e com vários valores.", "Guardar clientes com logótipo, valores acordados e condições de pagamento.",
                     "Saber de relance o que falta faturar, o que falta receber e o que já recebeste, mês a mês.", "Ver estatísticas e gráficos do teu ano.", "Ligar o calendário ao Google Calendar."))
        return shell("Sobre", f'<h1>Sobre {sn}</h1><p class="sub">Este site é um organizador pessoal para freelancers de audiovisual: guarda num só sítio os teus eventos, os teus clientes e o estado de cada fatura.</p>'
            f'<div class="card ab"><h2 style="margin-top:0">O que podes fazer</h2><ul>{li}</ul></div>'
            '<div class="card ab"><h2 style="margin-top:0">Importante</h2><p style="margin:0">Este site não emite faturas: a emissão continua a ser feita por ti, no teu programa de faturação. Aqui só acompanhas o estado de cada uma: por faturar, faturada ou paga.</p></div>'
            '<div class="card ab"><h2 style="margin-top:0">Privacidade</h2><p style="margin:0">Cada conta vê apenas os seus próprios eventos e clientes. Os dados ficam no servidor onde este site está instalado.</p></div>'
            f'<div class="card"><div class="cr"><b>Feito por Daniel Nunes</b><span class="m">·</span><b>Made in Portugal</b>{FLAG}</div></div>'
            f'<div class="card"><p style="margin:0 0 12px">Precisas de ajuda ou tens uma sugestão?</p><a class="btn p" href="/support">Falar com o suporte</a></div>', u, "/about")

    def support_get(self, u, p, g):
        parts = p.strip("/").split("/")
        if p == "/support": return self.support_page(u, ok=g("ok"))
        if len(parts) == 3 and parts[1] == "t": return self.ticket_page(u, parts[2], g("ok"))
        raise ValueError

    def support_page(self, u, ok="", err="", v=None):
        v = v or {}; fl = f'<p class="msg err">{eh(err)}</p>' if err else ""
        if u:
            ident = f'<p class="m">A escrever como <b>{e(u["name"] or u["username"])}</b> ({e(u["email"])}). As respostas aparecem aqui e também são enviadas para o teu email.</p>'
        else:
            ident = ('<p class="m">Ainda não tens conta ou não consegues entrar? Podes escrever na mesma: indica o teu email para podermos responder.</p>'
                     + fld("O teu nome", "name", val=v.get("name", ""), extra='maxlength="60" required autocomplete="name"')
                     + fld("O teu email (obrigatório, para podermos responder)", "email", "email", v.get("email", ""), 'maxlength="120" required autocomplete="email"'))
        form = ('<form class="f card" method="post" action="/support">' + ident + fld("Assunto", "subject", val=v.get("subject", ""), extra='maxlength="120" required')
                + f'<label>Mensagem</label><textarea name="body" rows="6" maxlength="3000" required>{e(v.get("body", ""))}</textarea>'
                '<input type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0">'
                '<p><button class="p">Enviar mensagem</button></p></form>')
        mine = ""
        if u:
            ts = rows("select * from tickets where user_id=? order by updated desc limit 30", (u["id"],))
            items = "".join(f'<div class="er {"todo" if t["unread_user"] else ""}"><a class="eh" href="/support/t/{t["token"]}"><div><b>{e(t["subject"])}</b>'
                            f'<small>{e(t["updated"])} · {"Fechada" if t["status"] == "closed" else "Aberta"}{" · <b>Nova resposta</b>" if t["unread_user"] else ""}</small></div></a></div>' for t in ts)
            mine = f'<h2>As tuas mensagens</h2><div class="list">{items or "<div class=empty>Ainda não enviaste nenhuma mensagem.</div>"}</div>'
        return shell("Suporte", f'<h1>Suporte</h1><p class="sub">Tens uma dúvida, um problema ou uma sugestão? Escreve-nos e respondemos o mais depressa possível.</p>{fl}{form}{mine}', u, "/support")

    def ticket_page(self, u, tok, ok=""):
        t = one("select * from tickets where token=?", (tok,))
        if not t: raise ValueError
        if t["unread_user"]: run("update tickets set unread_user=0 where id=?", (t["id"],))
        ms = rows("select * from tmsgs where ticket_id=? order by id", (t["id"],))
        bub = "".join(f'<div class="mg{" a" if m["from_admin"] else ""}"><small>{"Suporte" if m["from_admin"] else "Tu"} · {e(m["created"])}</small>{e(m["body"])}</div>' for m in ms)
        fl = f'<p class="msg ok">{eh("Mensagem enviada. A resposta aparece nesta página e é enviada para o teu email. Guarda este endereço para voltares cá." if ok == "sent" else "Resposta enviada.")}</p>' if ok in ("sent", "reply") else ""
        note = '<p class="m">Esta conversa está fechada. Se responderes, volta a abrir.</p>' if t["status"] == "closed" else ""
        return (shell("Suporte", f'<p><a class="m" href="/support">‹ Suporte</a></p><h1>{e(t["subject"])}</h1><p class="sub">Conversa com o suporte</p>{fl}<div class="msgs">{bub}</div>{note}'
            f'<form class="f card" method="post" action="/support/t/{e(tok)}/reply"><label>Responder</label><textarea name="body" rows="4" maxlength="3000" required></textarea>'
            '<p><button class="p">Enviar resposta</button></p></form>', u, "/support"))

    def support_post(self, u, p, f):
        parts = p.strip("/").split("/"); ip = "s" + self.client_address[0]; n, t0 = self.fails.get(ip, (0, 0)); lim = n >= 8 and time.time() - t0 < 3600
        host = BASE_URL or ("https://" if self.https() else "http://") + str(self.headers.get("Host"))
        if p == "/support":
            if f.get("website"): return self.go("/support")
            if lim: return self.out(self.support_page(u, err="Demasiadas mensagens. Tenta mais tarde.", v=f), 429)
            subj, body = f.get("subject", "").strip()[:120], f.get("body", "").strip()[:3000]
            name, em, uid = ((u["name"] or u["username"]), u["email"], u["id"]) if u else (f.get("name", "").strip()[:60], f.get("email", "").strip()[:120], None)
            if not subj or len(body) < 3 or not name or not re.match(EMAIL_RE, em): return self.out(self.support_page(u, err="Preenche o nome, um email válido, o assunto e a mensagem.", v=f), 400)
            self.fails[ip] = (n + 1 if time.time() - t0 < 3600 else 1, time.time()); tok = secrets.token_urlsafe(18); now = now_str()
            tid = run("insert into tickets(token,user_id,name,email,subject,lang,created,updated) values(?,?,?,?,?,?,?,?)", (tok, uid, name, em, subj, i18n.lang(), now, now))
            run("insert into tmsgs(ticket_id,from_admin,body,created) values(?,?,?,?)", (tid, 0, body, now))
            notify_admins(f"{SN()} · Nova mensagem de suporte", f"{name} <{em}>\nAssunto: {subj}\n\n{body}\n\n" + (f"Responder: {BASE_URL}/admin/support/{tid}\n" if BASE_URL else ""))
            if BASE_URL: mail_async(em, i18n.mail("ack_s", site=SN()), i18n.mail("ack_b", name=name, subject=subj, url=f"{BASE_URL}/support/t/{tok}"))
            return self.go(f"/support/t/{tok}?ok=sent")
        if len(parts) == 4 and parts[1] == "t" and parts[3] == "reply":
            t = one("select * from tickets where token=?", (parts[2],))
            if not t: raise ValueError
            body = f.get("body", "").strip()[:3000]
            if len(body) < 1 or lim: return self.go(f"/support/t/{parts[2]}")
            self.fails[ip] = (n + 1 if time.time() - t0 < 3600 else 1, time.time()); now = now_str()
            run("insert into tmsgs(ticket_id,from_admin,body,created) values(?,?,?,?)", (t["id"], 0, body, now))
            run("update tickets set status='open', updated=?, unread_admin=1 where id=?", (now, t["id"]))
            notify_admins(f"{SN()} · Nova mensagem de suporte", f"{t['name']} <{t['email']}>\nAssunto: {t['subject']}\n\n{body}\n\n" + (f"Responder: {BASE_URL}/admin/support/{t['id']}\n" if BASE_URL else ""))
            return self.go(f"/support/t/{parts[2]}?ok=reply")
        raise ValueError

    # ---- admin: suporte
    def a_support(self, u, flt="open", ok=""):
        flt = flt if flt in ("open", "closed", "all") else "open"
        cond = {"open": "status='open'", "closed": "status='closed'", "all": "1=1"}[flt]
        ts = rows(f"select t.*, (select body from tmsgs where ticket_id=t.id order by id desc limit 1) last, (select from_admin from tmsgs where ticket_id=t.id order by id desc limit 1) la "
                  f"from tickets t where {cond} order by unread_admin desc, updated desc limit 200")
        chips = "".join(f'<a class="{"on" if k == flt else ""}" href="/admin/support?f={k}">{n}</a>' for k, n in (("open", "Abertas"), ("closed", "Fechadas"), ("all", "Todos")))
        def row(t):
            bd = (' <span class="bd s">Nova</span>' if t["unread_admin"] else "") + (' <span class="bd a">Conta</span>' if t["user_id"] else ' <span class="bd">Visitante</span>') + (' <span class="bd">Fechada</span>' if t["status"] == "closed" else "")
            return (f'<div class="er {"todo" if t["unread_admin"] else ""}"><a class="eh" href="/admin/support/{t["id"]}"><span class="av">{e(ini(t["name"]))}</span><div><b>{e(t["subject"])}</b>{bd}'
                    f'<small>{e(t["name"])} · {e(t["email"])} · {e(t["updated"])}</small><small>{e((t["last"] or "")[:110])}</small></div></a></div>')
        return self.apage(u, "/admin/support", f'<h2 style="margin-top:0">Mensagens de suporte</h2><div class="chips">{chips}</div><div class="list">{"".join(row(t) for t in ts) or "<div class=empty>Sem mensagens.</div>"}</div>', ok)

    def a_ticket(self, u, tid, ok="", err=""):
        t = one("select * from tickets where id=?", (tid,))
        if not t: raise ValueError
        run("update tickets set unread_admin=0 where id=?", (t["id"],))
        ms = rows("select * from tmsgs where ticket_id=? order by id", (t["id"],)); base = f"/admin/support/{t['id']}"
        host = BASE_URL or ("https://" if self.https() else "http://") + str(self.headers.get("Host"))
        bub = "".join(f'<div class="mg{" a" if m["from_admin"] else ""}"><small>{"Suporte" if m["from_admin"] else e(t["name"])} · {e(m["created"])}</small>{e(m["body"])}</div>' for m in ms)
        who = ('<span class="bd a">Conta</span> ' if t["user_id"] else '<span class="bd">Visitante</span> ') + ('<span class="bd">Fechada</span>' if t["status"] == "closed" else "")
        btn = lambda act, label, cls="": f'<form method="post" action="{base}/{act}"><button class="{cls}">{label}</button></form>'
        return self.apage(u, "/admin/support", (
            f'<p><a href="/admin/support" class="m">‹ Todas as mensagens</a></p><div class="card"><b>{e(t["subject"])}</b> {who}<div class="m">{e(t["name"])} · <a href="mailto:{e(t["email"])}">{e(t["email"])}</a> · {e(t["created"])} · {e(i18n.LANGS.get(t["lang"], ""))}</div></div>'
            f'<div class="msgs">{bub}</div><form class="f card" method="post" action="{base}/reply"><label>Resposta</label><textarea name="body" rows="5" maxlength="3000" required></textarea>'
            f'<p class="m">A resposta aparece na página da conversa e é enviada por email para {e(t["email"])} (se o envio de emails estiver ativo).</p><p><button class="p">Enviar resposta</button></p></form>'
            f'<div class="card"><b>Link da conversa (para enviares manualmente, se precisares)</b><input readonly value="{e(host + "/support/t/" + t["token"])}" style="width:100%;margin-top:8px;padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)"></div>'
            f'<div class="row2">{btn("close", "Reabrir conversa" if t["status"] == "closed" else "Fechar conversa")}{btn("delete", "Apagar conversa", "d")}</div>'), ok, err)

    # ---- definições
    def settings(self, u, ok="", err=""):
        proto = "https" if self.https() else "http"; url = f'{BASE_URL or proto + "://" + str(self.headers.get("Host"))}/calendar.ics?k={u["ics"]}'
        msg = {"profile": "Dados guardados.", "password": "Palavra-passe alterada.", "ics": "Link novo gerado. O antigo deixou de funcionar."}.get(ok); m = f'<p class="msg ok">{msg}</p>' if msg else (f'<p class="msg err">{err}</p>' if err else "")
        return page("Conta", f'<h1>Conta</h1><p class="sub">Os teus dados e a tua segurança.</p>{m}<form class="f card" method="post" action="/settings/profile"><h2>Dados pessoais</h2>'
            + fld("Nome", "name", val=u["name"], extra="required") + fld("Email", "email", "email", u["email"], "required") + fld("Telemóvel", "phone", "tel", u["phone"] or "")
            + f'<p class="m">Utilizador: <b>{e(u["username"])}</b></p><p><button class="p">Guardar dados</button></p></form>'
            '<form class="f card" method="post" action="/settings/password"><h2>Alterar palavra-passe</h2>' + fld("Palavra-passe atual", "old", "password", extra='autocomplete="current-password" required')
            + fld("Nova palavra-passe (mínimo 8)", "p", "password", extra='autocomplete="new-password" minlength="8" required') + fld("Repetir nova palavra-passe", "p2", "password", extra='autocomplete="new-password" minlength="8" required') + '<p><button class="p">Alterar palavra-passe</button></p></form>'
            f'<div class="card"><h2>Google Calendar</h2><p class="m">Em Google Calendar → Outras agendas → A partir do URL, cola este link (só leitura). O Google precisa de conseguir aceder ao endereço, por isso só funciona se o site estiver acessível pela internet em HTTPS. Não partilhes este link.</p><input readonly value="{e(url)}" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)" id="icsurl"><form method="post" action="/settings/ics" style="margin-top:12px"><button>Gerar novo link</button> <span class="m">O link antigo deixa de funcionar.</span></form></div>'
            f'<div class="card"><h2>Idioma</h2><p class="m">Escolhe o idioma do site.</p>{langbar(True)}</div>'
            '<form method="post" action="/logout"><button>Terminar sessão</button></form><script nonce="__NONCE__">document.getElementById("icsurl").onclick=function(){this.select()}</script>', "/settings", u)

    def save_profile(self, u, f):
        name, em, ph = f.get("name", "").strip()[:60], f.get("email", "").strip(), f.get("phone", "").strip()[:30]
        if not name or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", em): return self.out(self.settings(u, err="Nome e email válidos são obrigatórios."), 400)
        try: run("update users set name=?, email=?, phone=? where id=?", (name, em, ph, u["id"]))
        except sqlite3.IntegrityError: return self.out(self.settings(u, err="Esse email já está a ser usado por outra conta."), 400)
        self.go("/settings?ok=profile")

    def save_password(self, u, f):
        if not check_pw(f.get("old", ""), u["pw"]): return self.out(self.settings(u, err="A palavra-passe atual está incorreta."), 400)
        if len(f.get("p", "")) < 8 or f.get("p") != f.get("p2"): return self.out(self.settings(u, err="A nova palavra-passe tem de ter 8+ caracteres e coincidir nos dois campos."), 400)
        run("update users set pw=? where id=?", (hash_pw(f["p"]), u["id"])); nu = one("select * from users where id=?", (u["id"],))
        self.go("/settings?ok=password", [session_cookie(nu, self.https())])

if __name__ == "__main__":
    init(); threading.Thread(target=backup_loop, daemon=True).start(); print("Claquete a escutar na porta 8000 | email:", "ativo" if smtp_ready() else "desligado", "| BASE_URL:", BASE_URL or "(vazio)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
