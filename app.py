#!/usr/bin/env python3
"""Claquete - organizador de eventos e faturas para freelancers (so biblioteca standard)."""
import os, re, ssl, time, math, hmac, html, hashlib, secrets, sqlite3, smtplib, calendar, threading
import datetime as dt
from email.message import EmailMessage
from email.utils import formataddr
from http import cookies
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB = os.environ.get("DB_PATH", "/data/claquete.db")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
INVITE = os.environ.get("INVITE_CODE", "")
MES = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split()

e = lambda s: html.escape("" if s is None else str(s))
today = lambda: dt.date.today()
D = dt.date.fromisoformat

def eur(v): return f"{(v or 0):,.2f}".replace(",", " ").replace(".", ",") + " €"
def short(v): return (f"{v / 1000:g}k".replace(".", ",") if v >= 1000 else f"{v:g}")
def num(s):
    try: return float(str(s).replace(" ", "").replace(",", "."))
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
    create table if not exists kv(k text primary key, v text);""")
    if not c.execute("select 1 from kv where k='secret'").fetchone():
        c.execute("insert into kv values('secret',?)", (secrets.token_hex(32),))
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
        m["From"] = formataddr(("Claquete", os.environ.get("SMTP_FROM") or user)); m["To"] = to; m["Subject"] = subject; m.set_content(body)
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

IC = {"home": '<path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
      "cal": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
      "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
      "users": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
      "chart": '<path d="M5 20V11M12 20V4M19 20v-6"/>',
      "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>'}
NAV = [("/", "Início", "home"), ("/calendar", "Calendário", "cal"), ("/events", "Eventos", "list"), ("/clients", "Clientes", "users"), ("/stats", "Estatísticas", "chart")]
LOGO = '<svg class="lg" viewBox="0 0 28 28"><rect width="28" height="28" rx="8" fill="#3b4cdb"/><rect x="6" y="7" width="16" height="3.6" rx="1.8" fill="#e5484d"/><rect x="6" y="12.2" width="11" height="3.6" rx="1.8" fill="#f0a020"/><rect x="9" y="17.4" width="13" height="3.6" rx="1.8" fill="#2fa56b"/></svg>'
def head(t): return '<!doctype html><html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#3b4cdb"><title>' + t + '</title><style>' + CSS + '</style></head><body>'

def page(title, body, active, u):
    nav = "".join(f'<a class="nl{" on" if h == active else ""}" href="{h}"><svg viewBox="0 0 24 24">{IC[i]}</svg><span>{n}</span></a>' for h, n, i in NAV)
    acct = f'<a class="nl acct{" on" if active == "/settings" else ""}" href="/settings"><svg viewBox="0 0 24 24">{IC["gear"]}</svg><span>{e(u["name"] or u["username"])}</span></a>'
    top = f'<div class="top"><a class="brand" href="/">{LOGO}Claquete</a><a class="me" href="/settings" aria-label="Conta">{e(ini(u["name"] or u["username"]))}</a></div>'
    return head(e(title) + " · Claquete") + f'<div class="shell"><nav class="side"><a class="brand" href="/">{LOGO}Claquete</a>{nav}<div class="sp"></div>{acct}</nav><div>{top}<main class="main">{body}</main></div></body></html>'

TL = ('<div class="tl"><div><i class="paid" style="left:2%;width:30%">Casamento</i><i class="inv" style="left:38%;width:24%">Conferência</i></div>'
      '<div><i class="todo" style="left:12%;width:26%">Videoclip</i><i class="paid" style="left:46%;width:40%">Festival · 3 dias</i></div>'
      '<div><i class="inv" style="left:0;width:20%">Spot</i><i class="todo" style="left:44%;width:30%">Institucional</i></div></div>'
      '<div class="lgd"><span style="--c:var(--todo)">por faturar</span><span style="--c:var(--inv)">faturada</span><span style="--c:var(--paid)">paga</span></div>')

def auth_page(title, inner):
    return (head(e(title) + " · Claquete") + f'<div class="auth"><section class="hero"><a class="brand" href="/">{LOGO}Claquete</a>'
            '<h1>Sabe sempre o que falta faturar e o que falta receber.</h1><p>Eventos, clientes e faturas num só sítio, feito para freelancers de audiovisual. Não emite faturas: só te ajuda a não perder nenhuma.</p>'
            f'{TL}</section><section class="ap"><div class="ac">{inner}</div></section></div></body></html>')

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
    meta = f'{drange(r["start_date"], r["end_date"])} · {e(r["cn"] or "sem cliente")}'
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
            if u and int(x) > time.time() and hmac.compare_digest(sig, sign(f"{i}.{x}.{u['pw'][-16:]}")): return u
        except Exception: pass
        return None

    def https(self): return self.headers.get("X-Forwarded-Proto") == "https"

    def out(self, body, code=200, ctype="text/html; charset=utf-8", hd=()):
        n = secrets.token_urlsafe(12); b = body.replace("__NONCE__", n).encode(); self.send_response(code)
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
        if p == "/calendar.ics": return self.ics(g("k"))
        u = self.user()
        if p in ("/login", "/register", "/forgot", "/reset"):
            if u: return self.go("/")
            return self.out({"/login": lambda: self.login_page(ok=g("ok")), "/register": self.register_page, "/forgot": self.forgot_page, "/reset": lambda: self.reset_page(g("t"))}[p]())
        if not u: return self.go("/login")
        parts = p.strip("/").split("/")
        try:
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
        org, sf = self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site")
        hosts = (self.headers.get("Host"), self.headers.get("X-Forwarded-Host"))
        if sf == "cross-site" or (not sf and org not in (None, "null") and urlparse(org).netloc not in hosts): return self.out("Pedido recusado", 403, "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
        self.fl = parse_qs(self.rfile.read(min(n, 200000)).decode(), keep_blank_values=True); f = {k: v[0] for k, v in self.fl.items()}
        p = urlparse(self.path).path; parts = p.strip("/").split("/")
        pub = {"/login": self.do_login, "/register": self.do_register, "/forgot": self.do_forgot, "/reset": self.do_reset}
        if p in pub: return pub[p](f)
        u = self.user()
        if not u: return self.go("/login")
        if p == "/logout": return self.go("/login", [("Set-Cookie", "s=; Max-Age=0; Path=/")])
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
        if p == "/settings/profile": return self.save_profile(u, f)
        if p == "/settings/password": return self.save_password(u, f)
        self.go("/")

    # ---- autenticação
    def login_page(self, err="", ok=""):
        msg = f'<p class="msg err">{err}</p>' if err else '<p class="msg ok">Palavra-passe alterada. Já podes entrar.</p>' if ok == "reset" else ""
        return auth_page("Entrar", f'<h1>Entrar</h1><p class="sub">Bem-vindo de volta.</p>{msg}<form class="f" method="post" action="/login">'
            + fld("Utilizador ou email", "u", extra='autocomplete="username" required autofocus') + fld("Palavra-passe", "p", "password", extra='autocomplete="current-password" required')
            + '<p><button class="p" style="width:100%">Entrar</button></p></form><p class="l2"><a href="/forgot">Esqueci-me da palavra-passe</a></p><p class="l2 m">Ainda não tens conta? <a href="/register">Criar conta</a></p>')

    def do_login(self, f):
        ip = self.client_address[0]; n, t = self.fails.get(ip, (0, 0))
        if n >= 8 and time.time() - t < 300: return self.out(self.login_page("Demasiadas tentativas. Espera 5 minutos."), 429)
        x = f.get("u", "").strip(); u = one("select * from users where username=? or email=?", (x, x))
        if u and check_pw(f.get("p", ""), u["pw"]):
            self.fails.pop(ip, None); return self.go("/", [session_cookie(u, self.https())])
        self.fails[ip] = (n + 1, time.time()); self.out(self.login_page("Utilizador ou palavra-passe incorretos."), 401)

    def register_page(self, err="", v=None):
        v = v or {}
        inv = fld("Código de convite", "code", extra="required") if INVITE else ""
        return auth_page("Criar conta", '<h1>Criar conta</h1><p class="sub">Demora menos de um minuto.</p>' + (f'<p class="msg err">{err}</p>' if err else "") + '<form class="f" method="post" action="/register">'
            + fld("Utilizador", "u", val=v.get("u", ""), extra='autocomplete="username" required autofocus') + fld("Email (para recuperar a palavra-passe)", "email", "email", v.get("email", ""), 'autocomplete="email" required')
            + fld("Palavra-passe (mínimo 8 caracteres)", "p", "password", extra='autocomplete="new-password" minlength="8" required') + fld("Repetir palavra-passe", "p2", "password", extra='autocomplete="new-password" minlength="8" required')
            + inv + '<p><button class="p" style="width:100%">Criar conta e entrar</button></p></form><p class="l2 m">Já tens conta? <a href="/login">Entrar</a></p>')

    def do_register(self, f):
        v = {"u": f.get("u", "").strip(), "email": f.get("email", "").strip()}; err = ""
        if INVITE and not hmac.compare_digest(f.get("code", ""), INVITE): err = "Código de convite incorreto."
        elif not re.match(r"^[\w.\-]{3,30}$", v["u"]): err = "O utilizador deve ter 3 a 30 caracteres (letras, números, . _ -)."
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v["email"]): err = "Email inválido."
        elif len(f.get("p", "")) < 8: err = "A palavra-passe tem de ter pelo menos 8 caracteres."
        elif f.get("p") != f.get("p2"): err = "As palavras-passe não coincidem."
        if not err:
            try: uid = run("insert into users(username,email,name,pw,ics,created) values(?,?,?,?,?,?)", (v["u"], v["email"], v["u"], hash_pw(f["p"]), secrets.token_hex(20), today().isoformat()))
            except sqlite3.IntegrityError: err = "Esse utilizador ou email já está registado."
        if err: return self.out(self.register_page(err, v), 400)
        mail_async(v["email"], "Bem-vindo à Claquete", f"Olá {v['u']},\n\nA tua conta na Claquete foi criada com sucesso.\n\nUtilizador: {v['u']}\n" + (f"Entrar: {BASE_URL}\n" if BASE_URL else "") + "\nSe não foste tu a criar esta conta, ignora este email.")
        self.go("/", [session_cookie(one("select * from users where id=?", (uid,)), self.https())])

    def forgot_page(self, sent=False):
        if sent: return auth_page("Recuperar", '<h1>Verifica o teu email</h1><p class="sub">Se esse email estiver registado, enviámos um link para definires uma nova palavra-passe. O link é válido durante 1 hora.</p><p class="l2"><a href="/login">Voltar a entrar</a></p>')
        return auth_page("Recuperar", '<h1>Recuperar palavra-passe</h1><p class="sub">Indica o email da tua conta.</p><form class="f" method="post" action="/forgot">' + fld("Email", "email", "email", extra="required autofocus")
            + '<p><button class="p" style="width:100%">Enviar link</button></p></form><p class="l2"><a href="/login">Voltar</a></p>')

    def do_forgot(self, f):
        ip = "f" + self.client_address[0]; n, t = self.fails.get(ip, (0, 0))
        if n >= 5 and time.time() - t < 900: return self.out(self.forgot_page(True))
        self.fails[ip] = (n + 1 if time.time() - t < 900 else 1, time.time())
        u = one("select * from users where email=?", (f.get("email", "").strip(),))
        if u:
            tok = secrets.token_urlsafe(32); run("delete from resets where user_id=? or exp<?", (u["id"], time.time()))
            run("insert into resets values(?,?,?)", (hashlib.sha256(tok.encode()).hexdigest(), u["id"], int(time.time()) + 3600))
            if BASE_URL and smtp_ready():
                mail_async(u["email"], "Recuperar palavra-passe · Claquete", f"Olá {u['name']},\n\nPara definires uma nova palavra-passe abre este link (válido 1 hora):\n{BASE_URL}/reset?t={tok}\n\nSe não pediste isto, ignora este email.")
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
            '<div class="strip">' + tile("var(--todo)", "Por faturar", s(a), f"{len(a)} eventos") + tile("var(--inv)", "Faturado, por receber", s(b), f"{len(b)} eventos")
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
        rowsh = "".join(f'<div class="it"><input name="label" list="sug" value="{e(l)}" placeholder="Descrição"><input name="amt" inputmode="decimal" value="{f"{a:g}".replace(".", ",")}" placeholder="0,00"></div>' for l, a in (its or [("Diária", 0)]))
        dele = f'<details><summary>Apagar evento</summary><form method="post" action="/event/{v["id"]}/delete"><p class="m">Esta ação não pode ser desfeita.</p><button class="d">Confirmar: apagar</button></form></details>' if v else ""
        ck = lambda x: "checked" if x else ""
        return page("Evento", f'<h1>{"Editar" if v else "Novo"} evento</h1><form class="f card" method="post" action="/event/save"><input type="hidden" name="id" value="{v["id"] if v else ""}">'
            + fld("Título", "title", val=v["title"] if v else "", extra="required" + ("" if v else " autofocus"))
            + f'<div class="g2"><div><label>Data de início</label><input type="date" id="sd" name="start" value="{sd}" required></div><div><label>Data de fim</label><input type="date" id="ed" name="end" value="{ed}" required></div></div>'
            f'<label>Cliente</label><select id="cs" name="client_id"><option value="">— sem cliente —</option>{cl}</select><div class="info" id="ci" hidden></div>'
            f'<label>Valores</label><div id="items">{rowsh}</div><button type="button" id="add">+ Adicionar linha</button><div class="sum">Total<span id="tot">0,00 €</span></div>'
            '<datalist id="sug"><option value="Diária"><option value="Meia diária"><option value="Hora extra"><option value="Aluguer de equipamento"><option value="Deslocação"><option value="Edição"></datalist>'
            + f'<div class="g2"><div><label>Data da fatura (vazio = por faturar)</label><input type="date" name="invoice_date" value="{e(v["invoice_date"] if v else "")}"></div><div><label>N.º da fatura</label><input name="invoice_no" value="{e(v["invoice_no"] if v else "")}"></div></div>'
            f'<label class="c" style="margin-top:14px"><input type="checkbox" name="paid" {ck(v and v["paid"])}>Fatura paga (já recebi)</label><label>Notas</label><textarea name="notes" rows="3">{e(v["notes"] if v else "")}</textarea>'
            '<p><button class="p">Guardar</button> <a class="btn" href="/events">Cancelar</a></p></form>' + dele
            + '<script nonce="__NONCE__">(function(){var L=document.getElementById("items"),T=document.getElementById("tot");function tot(){var s=0;L.querySelectorAll("[name=amt]").forEach(function(i){s+=parseFloat(i.value.replace(",","."))||0});T.textContent=s.toFixed(2).replace(".",",")+" €"}'
            'L.addEventListener("input",tot);tot();document.getElementById("add").onclick=function(){var d=document.createElement("div");d.className="it";d.innerHTML=\'<input name="label" list="sug" placeholder="Descrição"><input name="amt" inputmode="decimal" placeholder="0,00">\';L.appendChild(d);d.firstChild.focus()};'
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
        l = "".join(f'<div class="er"><a class="eh" href="/client/{c["id"]}">{avatar(c["name"], c["logo"])}<div><b>{e(c["name"])}</b><small>{e(c["rate"]) or "sem valores definidos"} · {c["n"]} eventos</small></div></a><span class="amt">{eur(c["due"]) if c["due"] else ""}</span></div>' for c in r)
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
        L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Claquete//PT", "X-WR-CALNAME:Claquete"]
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
            + tile("var(--inv)", "Dias trabalhados", f"{td:g}", f"{sum(cnt)} eventos") + tile("var(--todo)", "Melhor mês", MES[best].capitalize() if best is not None else "—", eur(fat[best]) if best is not None else "") + '</div>'
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

    # ---- definições
    def settings(self, u, ok="", err=""):
        proto = "https" if self.https() else "http"; url = f'{BASE_URL or proto + "://" + str(self.headers.get("Host"))}/calendar.ics?k={u["ics"]}'
        msg = {"profile": "Dados guardados.", "password": "Palavra-passe alterada."}.get(ok); m = f'<p class="msg ok">{msg}</p>' if msg else (f'<p class="msg err">{err}</p>' if err else "")
        return page("Conta", f'<h1>Conta</h1><p class="sub">Os teus dados e a tua segurança.</p>{m}<form class="f card" method="post" action="/settings/profile"><h2>Dados pessoais</h2>'
            + fld("Nome", "name", val=u["name"], extra="required") + fld("Email", "email", "email", u["email"], "required") + fld("Telemóvel", "phone", "tel", u["phone"] or "")
            + f'<p class="m">Utilizador: <b>{e(u["username"])}</b></p><p><button class="p">Guardar dados</button></p></form>'
            '<form class="f card" method="post" action="/settings/password"><h2>Alterar palavra-passe</h2>' + fld("Palavra-passe atual", "old", "password", extra='autocomplete="current-password" required')
            + fld("Nova palavra-passe (mínimo 8)", "p", "password", extra='autocomplete="new-password" minlength="8" required') + fld("Repetir nova palavra-passe", "p2", "password", extra='autocomplete="new-password" minlength="8" required') + '<p><button class="p">Alterar palavra-passe</button></p></form>'
            f'<div class="card"><h2>Google Calendar</h2><p class="m">Em Google Calendar → Outras agendas → A partir do URL, cola este link (só leitura). O Google precisa de conseguir aceder ao endereço, por isso só funciona se o site estiver acessível pela internet em HTTPS. Não partilhes este link.</p><input readonly value="{e(url)}" style="width:100%;padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)" onclick="this.select()"></div>'
            '<form method="post" action="/logout"><button>Terminar sessão</button></form>', "/settings", u)

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
    init(); print("Claquete a escutar na porta 8000 | email:", "ativo" if smtp_ready() else "desligado", "| BASE_URL:", BASE_URL or "(vazio)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
