#!/usr/bin/env python3
"""Organizador de eventos e faturas - so biblioteca standard do Python."""
import os, sqlite3, hmac, hashlib, secrets, time, html, calendar, datetime as dt
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from http import cookies

DB = os.environ.get("DB_PATH", "/data/app.db")
TODAY = lambda: dt.date.today()
e = lambda s: html.escape("" if s is None else str(s))
eur = lambda v: f"{(v or 0):,.2f}".replace(",", " ").replace(".", ",") + " €"

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("pragma foreign_keys=on"); return c

def rows(q, a=()):
    c = db(); r = c.execute(q, a).fetchall(); c.close(); return r

def run(q, a=()):
    c = db(); cur = c.execute(q, a); c.commit(); i = cur.lastrowid; c.close(); return i

def hash_pw(p, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt, 300000).hex()

def check_pw(p, stored):
    s, _ = stored.split("$")
    return hmac.compare_digest(hash_pw(p, bytes.fromhex(s)), stored)

def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = db()
    c.executescript("""
    create table if not exists users(id integer primary key, name text unique, pw text);
    create table if not exists clients(id integer primary key, name text not null, nif text, contact text, rate text, terms text, notes text);
    create table if not exists events(id integer primary key, date text not null, title text not null,
      client_id integer references clients(id) on delete set null, amount real default 0, invoice_by text,
      invoice_no text, invoiced integer default 0, paid integer default 0, notes text);
    create table if not exists kv(k text primary key, v text);""")
    if os.environ.get("RESET_USERS") == "1":
        c.execute("delete from users")
    for k in ("secret", "ics"):
        if not c.execute("select 1 from kv where k=?", (k,)).fetchone():
            c.execute("insert into kv values(?,?)", (k, secrets.token_hex(24)))
    c.commit(); c.close()

def kv(k): return rows("select v from kv where k=?", (k,))[0]["v"]
def has_users(): return bool(rows("select 1 from users"))

def session_cookie(uid):
    x = int(time.time()) + 30 * 86400
    return ("Set-Cookie", f"s={uid}.{x}.{sign(f'{uid}.{x}')}; Max-Age=2592000; Path=/; HttpOnly; SameSite=Strict")

def sign(s): return hmac.new(kv("secret").encode(), s.encode(), hashlib.sha256).hexdigest()

CSS = """
:root{--bg:#eef1f4;--fg:#14202b;--card:#fff;--mut:#5d6b78;--ac:#0f766e;--bd:#d5dce2;--todo:#c2410c;--inv:#a16207;--ok:#15803d}
@media(prefers-color-scheme:dark){:root{--bg:#10171d;--fg:#e6ecf1;--card:#18222b;--mut:#93a1ae;--bd:#2b3945;--ac:#2dd4bf;--todo:#fb923c;--inv:#facc15;--ok:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,sans-serif}
main{max-width:920px;margin:0 auto;padding:12px 14px 60px}h1{font-size:1.4rem;margin:.6em 0}h2{font-size:1.1rem;margin:1.4em 0 .4em}
nav{display:flex;gap:4px;flex-wrap:wrap;background:var(--card);border-bottom:1px solid var(--bd);padding:8px 10px;position:sticky;top:0;z-index:5}
nav a,nav button{padding:8px 12px;border-radius:8px;text-decoration:none;color:var(--fg);background:none;border:0;font:inherit;cursor:pointer}
nav a.on{background:var(--ac);color:#fff}nav form{margin-left:auto}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px;margin:8px 0}
.row{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.row a.t{color:var(--fg);font-weight:600;text-decoration:none}.m{color:var(--mut);font-size:.9rem}
.tot{display:flex;gap:10px;flex-wrap:wrap}.tot div{flex:1 1 140px}.tot b{display:block;font-size:1.4rem}
.late{color:var(--todo);font-weight:600}
button,.btn{font:inherit;padding:9px 14px;border-radius:8px;border:1px solid var(--bd);background:var(--card);color:var(--fg);cursor:pointer;text-decoration:none;display:inline-block}
button.p,.btn.p{background:var(--ac);color:#fff;border-color:var(--ac)}button.on{background:var(--ok);color:#fff;border-color:var(--ok)}button.d{color:var(--todo)}
form.f label{display:block;margin:10px 0 3px;font-weight:600}form.f input,form.f select,form.f textarea{width:100%;font:inherit;padding:9px;border-radius:8px;border:1px solid var(--bd);background:var(--bg);color:var(--fg)}
form.f input[type=checkbox]{width:auto;margin-right:8px}form.f label.c{font-weight:400}
.chips a{margin-right:6px}.tg{display:flex;gap:6px}.tg form{margin:0}
.cal{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px}.cal .h{text-align:center;font-size:.8rem;color:var(--mut)}
.day{background:var(--card);border:1px solid var(--bd);min-height:68px;padding:2px;font-size:.72rem;overflow:hidden}.day.out{opacity:.45}.day.today{outline:2px solid var(--ac)}
.dn{color:var(--mut);text-decoration:none;display:block}.ev{display:block;margin-top:2px;padding:1px 3px;border-radius:4px;color:#fff;text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ev.todo{background:var(--todo)}.ev.inv{background:var(--inv)}.ev.paid{background:var(--ok)}.lg span{margin-right:12px}
details summary{cursor:pointer;color:var(--todo);margin-top:14px}
"""

def page(title, body, active="", logged=True):
    nav = ""
    if logged:
        L = [("/", "Início"), ("/calendar", "Calendário"), ("/events", "Eventos"), ("/clients", "Clientes")]
        nav = "<nav>" + "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{n}</a>' for h, n in L) + \
              '<form method="post" action="/logout"><button>Sair</button></form></nav>'
    return f'<!doctype html><html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{CSS}</style></head><body>{nav}<main>{body}</main></body></html>'

def state(r): return "paid" if r["paid"] else "inv" if r["invoiced"] else "todo"
EV_SQL = "select e.*, c.name cn from events e left join clients c on c.id=e.client_id "

def tog(r, nxt):
    def b(f, label, on):
        return f'<form method="post" action="/toggle/{r["id"]}/{f}"><input type="hidden" name="next" value="{e(nxt)}"><button class="{"on" if on else ""}">{"✓ " if on else ""}{label}</button></form>'
    return '<div class="tg">' + b("invoiced", "Faturada", r["invoiced"]) + b("paid", "Paga", r["paid"]) + "</div>"

def ev_row(r, nxt):
    late = ""
    if not r["invoiced"] and r["invoice_by"] and r["invoice_by"] < TODAY().isoformat():
        late = f' <span class="late">· faturar até {e(r["invoice_by"])} (atrasado)</span>'
    elif not r["invoiced"] and r["invoice_by"]:
        late = f' · faturar até {e(r["invoice_by"])}'
    return (f'<div class="card"><div class="row"><div><a class="t" href="/event/{r["id"]}">{e(r["title"])}</a>'
            f'<div class="m">{e(r["date"])} · {e(r["cn"] or "sem cliente")} · {eur(r["amount"])}{late}</div></div>{tog(r, nxt)}</div></div>')

class H(BaseHTTPRequestHandler):
    fails = {}
    def log_message(self, *a): pass

    def uid(self):
        m = cookies.SimpleCookie(self.headers.get("Cookie", "")).get("s")
        try:
            u, x, sig = m.value.split(".")
            if hmac.compare_digest(sig, sign(f"{u}.{x}")) and int(x) > time.time(): return int(u)
        except Exception: pass
        return None

    def out(self, body, code=200, ctype="text/html; charset=utf-8", hd=()):
        b = body.encode(); self.send_response(code)
        for k, v in (("Content-Type", ctype), ("Content-Length", str(len(b))), ("X-Frame-Options", "DENY"),
                     ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "same-origin"),
                     ("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'"), *hd):
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def go(self, to, hd=()):
        self.send_response(303); self.send_header("Location", to)
        for k, v in hd: self.send_header(k, v)
        self.end_headers()

    def safe(self, n): return n if n.startswith("/") and not n.startswith("//") else "/"

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); p = u.path
        if p == "/calendar.ics":
            if hmac.compare_digest(q.get("k", [""])[0], kv("ics")): return self.ics()
            return self.out("Não autorizado", 403, "text/plain")
        if p == "/register": return self.go("/login") if has_users() else self.out(self.register_page())
        if p == "/login": return self.go("/register") if not has_users() else self.out(self.login_page())
        if not self.uid(): return self.go("/login")
        g = lambda k, d="": q.get(k, [d])[0]
        parts = p.strip("/").split("/")
        try:
            if p == "/": return self.out(self.home())
            if p == "/calendar": return self.out(self.cal(g("m")))
            if p == "/events": return self.out(self.events(g("f", "todos")))
            if p == "/clients": return self.out(self.clients())
            if parts[0] == "event" and len(parts) == 2: return self.out(self.event_form(parts[1], g("date")))
            if parts[0] == "client" and len(parts) == 2: return self.out(self.client_form(parts[1]))
        except (ValueError, IndexError): pass
        self.out(page("Não encontrado", "<h1>Página não encontrada</h1>"), 404)

    def do_POST(self):
        org, sf = self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site")
        hosts = (self.headers.get("Host"), self.headers.get("X-Forwarded-Host"))
        if (sf == "cross-site") or (not sf and org not in (None, "null") and urlparse(org).netloc not in hosts):
            return self.out("Pedido recusado", 403, "text/plain")
        n = int(self.headers.get("Content-Length", 0) or 0)
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 100000)).decode()).items()}
        p = urlparse(self.path).path; parts = p.strip("/").split("/")
        if p == "/login": return self.do_login(f)
        if p == "/register": return self.do_register(f)
        if not self.uid(): return self.go("/login")
        if p == "/logout": return self.go("/login", [("Set-Cookie", "s=; Max-Age=0; Path=/")])
        nxt = self.safe(f.get("next", "/"))
        if parts[0] == "toggle" and len(parts) == 3 and parts[2] in ("invoiced", "paid"):
            r = rows("select * from events where id=?", (parts[1],))
            if r:
                new = 1 - r[0][parts[2]]
                inv, paid = (r[0]["invoiced"], r[0]["paid"])
                if parts[2] == "paid": paid = new; inv = 1 if new else inv
                else: inv = new; paid = 0 if not new else paid
                run("update events set invoiced=?, paid=? where id=?", (inv, paid, parts[1]))
            return self.go(nxt)
        if p == "/event/save":
            try: amt = float(f.get("amount", "0").replace(",", ".") or 0)
            except ValueError: amt = 0
            paid = 1 if f.get("paid") else 0; inv = 1 if (f.get("invoiced") or paid) else 0
            vals = (f.get("date") or TODAY().isoformat(), f.get("title", "").strip() or "Evento", f.get("client_id") or None, amt,
                    f.get("invoice_by") or None, f.get("invoice_no", "").strip(), inv, paid, f.get("notes", ""))
            if f.get("id"): run("update events set date=?,title=?,client_id=?,amount=?,invoice_by=?,invoice_no=?,invoiced=?,paid=?,notes=? where id=?", vals + (f["id"],))
            else: run("insert into events(date,title,client_id,amount,invoice_by,invoice_no,invoiced,paid,notes) values(?,?,?,?,?,?,?,?,?)", vals)
            return self.go("/events")
        if parts[0] == "event" and len(parts) == 3 and parts[2] == "delete":
            run("delete from events where id=?", (parts[1],)); return self.go("/events")
        if p == "/client/save":
            vals = tuple(f.get(k, "").strip() for k in ("name", "nif", "contact", "rate", "terms", "notes"))
            if not vals[0]: return self.go("/clients")
            if f.get("id"): run("update clients set name=?,nif=?,contact=?,rate=?,terms=?,notes=? where id=?", vals + (f["id"],))
            else: run("insert into clients(name,nif,contact,rate,terms,notes) values(?,?,?,?,?,?)", vals)
            return self.go("/clients")
        if parts[0] == "client" and len(parts) == 3 and parts[2] == "delete":
            run("delete from clients where id=?", (parts[1],)); return self.go("/clients")
        self.go("/")

    # ---- login
    def login_page(self, err=""):
        return page("Entrar", f'<h1>Organizador de faturas</h1>{f"<p class=late>{err}</p>" if err else ""}'
            '<form class="f card" method="post" action="/login"><label>Utilizador</label><input name="u" autocomplete="username" required autofocus>'
            '<label>Palavra-passe</label><input name="p" type="password" autocomplete="current-password" required><p><button class="p">Entrar</button></p></form>', logged=False)

    def do_login(self, f):
        ip = self.client_address[0]; n, t = self.fails.get(ip, (0, 0))
        if n >= 5 and time.time() - t < 300: return self.out(self.login_page("Demasiadas tentativas. Espera 5 minutos."), 429)
        r = rows("select * from users where name=?", (f.get("u", ""),))
        if r and check_pw(f.get("p", ""), r[0]["pw"]):
            self.fails.pop(ip, None)
            return self.go("/", [session_cookie(r[0]["id"])])
        self.fails[ip] = (n + 1, time.time())
        self.out(self.login_page("Utilizador ou palavra-passe incorretos."), 401)

    def register_page(self, err=""):
        return page("Criar conta", f'<h1>Criar a tua conta</h1><p class="m">Só podes fazer isto uma vez. Depois do registo, esta página fecha.</p>{f"<p class=late>{err}</p>" if err else ""}'
            '<form class="f card" method="post" action="/register"><label>Utilizador</label><input name="u" autocomplete="username" required autofocus>'
            '<label>Palavra-passe (mínimo 8 caracteres)</label><input name="p" type="password" autocomplete="new-password" minlength="8" required>'
            '<label>Repetir palavra-passe</label><input name="p2" type="password" autocomplete="new-password" minlength="8" required><p><button class="p">Criar conta e entrar</button></p></form>', logged=False)

    def do_register(self, f):
        if has_users(): return self.go("/login")
        u, p = f.get("u", "").strip(), f.get("p", "")
        if not u: return self.out(self.register_page("Escolhe um utilizador."), 400)
        if len(p) < 8: return self.out(self.register_page("A palavra-passe tem de ter pelo menos 8 caracteres."), 400)
        if p != f.get("p2"): return self.out(self.register_page("As palavras-passe não coincidem."), 400)
        uid = run("insert into users(name,pw) values(?,?)", (u, hash_pw(p)))
        self.go("/", [session_cookie(uid)])

    # ---- pages
    def home(self):
        a = rows(EV_SQL + "where invoiced=0 order by coalesce(invoice_by,e.date)")
        b = rows(EV_SQL + "where invoiced=1 and paid=0 order by e.date")
        up = rows(EV_SQL + "where e.date>=? order by e.date limit 5", (TODAY().isoformat(),))
        s = lambda l: sum(x["amount"] or 0 for x in l)
        body = f'<h1>Início</h1><div class="card tot"><div>Por faturar<b>{eur(s(a))}</b><span class="m">{len(a)} eventos</span></div><div>Faturado, por receber<b>{eur(s(b))}</b><span class="m">{len(b)} eventos</span></div></div>'
        body += "<h2>Por faturar</h2>" + ("".join(ev_row(r, "/") for r in a) or '<p class="m">Nada por faturar.</p>')
        body += "<h2>Por receber</h2>" + ("".join(ev_row(r, "/") for r in b) or '<p class="m">Nada por receber.</p>')
        body += "<h2>Próximos eventos</h2>" + ("".join(ev_row(r, "/") for r in up) or '<p class="m">Sem eventos futuros.</p>')
        body += f'<p><a class="btn p" href="/event/new">Novo evento</a></p>'
        return page("Início", body, "/")

    def events(self, f):
        w = {"faturar": "where invoiced=0", "receber": "where invoiced=1 and paid=0", "pagos": "where paid=1"}.get(f, "")
        r = rows(EV_SQL + w + " order by e.date desc")
        chips = "".join(f'<a class="btn {"p" if f == k else ""}" href="/events?f={k}">{n}</a>' for k, n in
                        [("todos", "Todos"), ("faturar", "Por faturar"), ("receber", "Por receber"), ("pagos", "Pagos")])
        return page("Eventos", f'<h1>Eventos</h1><p class="chips">{chips}</p><p><a class="btn p" href="/event/new">Novo evento</a></p>'
                    + ("".join(ev_row(x, f"/events?f={f}") for x in r) or '<p class="m">Sem eventos.</p>'), "/events")

    def event_form(self, i, date=""):
        r = rows(EV_SQL + "where e.id=?", (i,)) if i != "new" else []
        if i != "new" and not r: raise ValueError
        v = r[0] if r else {"id": "", "date": date or TODAY().isoformat(), "title": "", "client_id": None, "amount": "", "invoice_by": "", "invoice_no": "", "invoiced": 0, "paid": 0, "notes": ""}
        opts = '<option value="">— sem cliente —</option>' + "".join(
            f'<option value="{c["id"]}" {"selected" if c["id"] == v["client_id"] else ""}>{e(c["name"])}</option>' for c in rows("select * from clients order by name"))
        info = ""
        if v["client_id"]:
            c = rows("select * from clients where id=?", (v["client_id"],))[0]
            info = f'<div class="card"><b>{e(c["name"])}</b><div class="m">Valores: {e(c["rate"]) or "—"}<br>Condições: {e(c["terms"]) or "—"}</div></div>'
        ck = lambda x: "checked" if x else ""
        dele = f'<details><summary>Apagar evento</summary><form method="post" action="/event/{v["id"]}/delete"><button class="d">Confirmar: apagar</button></form></details>' if v["id"] else ""
        return page("Evento", f'<h1>{"Editar" if v["id"] else "Novo"} evento</h1>{info}<form class="f card" method="post" action="/event/save"><input type="hidden" name="id" value="{v["id"]}">'
            f'<label>Título</label><input name="title" value="{e(v["title"])}" required><label>Data do evento</label><input type="date" name="date" value="{e(v["date"])}" required>'
            f'<label>Cliente</label><select name="client_id">{opts}</select><label>Valor (€)</label><input name="amount" inputmode="decimal" value="{e(v["amount"])}">'
            f'<label>Faturar até (opcional)</label><input type="date" name="invoice_by" value="{e(v["invoice_by"])}"><label>N.º da fatura (opcional)</label><input name="invoice_no" value="{e(v["invoice_no"])}">'
            f'<label class="c"><input type="checkbox" name="invoiced" {ck(v["invoiced"])}>Fatura passada</label><label class="c"><input type="checkbox" name="paid" {ck(v["paid"])}>Fatura paga</label>'
            f'<label>Notas</label><textarea name="notes" rows="3">{e(v["notes"])}</textarea><p><button class="p">Guardar</button> <a class="btn" href="/events">Cancelar</a></p></form>{dele}', "/events")

    def clients(self):
        r = rows("select c.*, (select count(*) from events where client_id=c.id) n, (select coalesce(sum(amount),0) from events where client_id=c.id and paid=0) due from clients c order by name")
        l = "".join(f'<div class="card"><a class="t" href="/client/{c["id"]}">{e(c["name"])}</a><div class="m">{e(c["rate"]) or "sem valores definidos"} · {c["n"]} eventos · por receber {eur(c["due"])}</div></div>' for c in r)
        return page("Clientes", f'<h1>Clientes</h1><p><a class="btn p" href="/client/new">Novo cliente</a></p>{l or "<p class=m>Ainda sem clientes.</p>"}', "/clients")

    def client_form(self, i):
        r = rows("select * from clients where id=?", (i,)) if i != "new" else []
        if i != "new" and not r: raise ValueError
        v = r[0] if r else {k: "" for k in ("id", "name", "nif", "contact", "rate", "terms", "notes")}
        fld = lambda k, lab, area=False: f'<label>{lab}</label>' + (f'<textarea name="{k}" rows="3">{e(v[k])}</textarea>' if area else f'<input name="{k}" value="{e(v[k])}">')
        hist = ""
        if v["id"]:
            hist = "<h2>Eventos deste cliente</h2>" + "".join(ev_row(x, f"/client/{i}") for x in rows(EV_SQL + "where client_id=? order by e.date desc", (i,)))
        dele = f'<details><summary>Apagar cliente</summary><form method="post" action="/client/{v["id"]}/delete"><p class="m">Os eventos ficam, mas sem cliente.</p><button class="d">Confirmar: apagar</button></form></details>' if v["id"] else ""
        return page("Cliente", f'<h1>{"Editar" if v["id"] else "Novo"} cliente</h1><form class="f card" method="post" action="/client/save"><input type="hidden" name="id" value="{v["id"]}">'
            f'<label>Nome</label><input name="name" value="{e(v["name"])}" required>{fld("nif", "NIF")}{fld("contact", "Contacto")}{fld("rate", "Valores acordados (ex.: 250 €/dia)")}{fld("terms", "Condições de pagamento", True)}{fld("notes", "Notas", True)}'
            f'<p><button class="p">Guardar</button> <a class="btn" href="/clients">Cancelar</a></p></form>{hist}{dele}', "/clients")

    def cal(self, m):
        try: first = dt.datetime.strptime(m, "%Y-%m").date()
        except ValueError: first = TODAY().replace(day=1)
        prev = (first - dt.timedelta(days=1)).strftime("%Y-%m"); nxt = (first + dt.timedelta(days=32)).replace(day=1).strftime("%Y-%m")
        weeks = calendar.Calendar(0).monthdatescalendar(first.year, first.month)
        evs = rows(EV_SQL + "where e.date between ? and ?", (weeks[0][0].isoformat(), weeks[-1][-1].isoformat()))
        by = {}
        for r in evs: by.setdefault(r["date"], []).append(r)
        cells = "".join(f'<div class="h">{d}</div>' for d in ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"))
        for wk in weeks:
            for d in wk:
                items = "".join(f'<a class="ev {state(r)}" href="/event/{r["id"]}">{e(r["title"])}</a>' for r in by.get(d.isoformat(), []))
                cells += f'<div class="day{" out" if d.month != first.month else ""}{" today" if d == TODAY() else ""}"><a class="dn" href="/event/new?date={d.isoformat()}">{d.day}</a>{items}</div>'
        meses = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split()
        return page("Calendário", f'<div class="row"><a class="btn" href="/calendar?m={prev}">‹</a><h1>{meses[first.month - 1]} {first.year}</h1><a class="btn" href="/calendar?m={nxt}">›</a></div>'
            f'<div class="cal">{cells}</div><p class="m lg"><span>🟧 por faturar</span><span>🟨 faturado</span><span>🟩 pago</span></p><p class="m">Toca num dia para criar um evento.</p>'
            f'<h2>Subscrever no Google Calendar</h2><p class="m">Google Calendar → Outras agendas → A partir do URL, e cola: <code>https://O_TEU_DOMINIO/calendar.ics?k={kv("ics")}</code></p>', "/calendar")

    def ics(self):
        L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Organizador//PT", "X-WR-CALNAME:Eventos"]
        for r in rows(EV_SQL + "order by e.date"):
            d = r["date"].replace("-", ""); nx = (dt.date.fromisoformat(r["date"]) + dt.timedelta(days=1)).strftime("%Y%m%d")
            st = "paga" if r["paid"] else "faturada" if r["invoiced"] else "por faturar"
            esc = lambda s: str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
            L += ["BEGIN:VEVENT", f"UID:ev{r['id']}@organizador", f"DTSTAMP:{dt.datetime.utcnow():%Y%m%dT%H%M%SZ}", f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{nx}",
                  f"SUMMARY:{esc(r['title'])}", f"DESCRIPTION:{esc((r['cn'] or '') + ' | ' + eur(r['amount']) + ' | ' + st)}", "END:VEVENT"]
        self.out("\r\n".join(L + ["END:VCALENDAR"]) + "\r\n", 200, "text/calendar; charset=utf-8")

if __name__ == "__main__":
    init()
    print("A escutar na porta 8000", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
