"""Ilustracoes animadas (SVG + CSS) para o guia 'Como funciona'. Sem imagens externas, sem JS."""

NAV = ["Início", "Calendário", "Eventos", "Clientes", "Chat", "Estatísticas"]
ICON = {  # pequenos icones (caminhos 18x18 centrados em 0,0)
    0: '<path d="M-7 1l7-6 7 6v6h-4v-4h-6v4h-4z"/>', 1: '<rect x="-7" y="-6" width="14" height="13" rx="2"/><path d="M-7 -1h14M-3 -8v3M3 -8v3"/>',
    2: '<path d="M-7 -5h14M-7 0h14M-7 5h14"/>', 3: '<circle cx="0" cy="-3" r="3.5"/><path d="M-7 7c0-4 3-5 7-5s7 1 7 5"/>',
    4: '<path d="M7 0a6.5 6 0 0 1-9.5 5.3L-7 7l.8-3.6A6.5 6 0 1 1 7 0z"/>', 5: '<path d="M-6 6v-5M0 6v-11M6 6v-8"/>'}

def cur(pts, extra=""):
    """cursor animado que passa por 4 pontos (inicio + 3 cliques)"""
    st = ";".join(f"--x{i}:{x}px;--y{i}:{y}px" for i, (x, y) in enumerate(pts))
    return (f'<g class="cur" style="{st}"{extra}><circle class="rip" r="14"/>'
            '<path d="M0 0l0 17 4.4-4 3.2 7.2 3-1.3-3.1-7 6.2-.4z" fill="#111" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/></g>')

def txt(x, y, s, size=11, w=500, fill="var(--ink)", anchor="start", cls=""):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{w}" fill="{fill}" text-anchor="{anchor}" class="{cls}">{s}</text>'

def box(x, y, w, h, fill="var(--sf)", stroke="var(--line)", rx=8, cls=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" class="{cls}"/>'

def btn(x, y, w, h, label, cls="", primary=True):
    f = "var(--brand)" if primary else "var(--sf)"; c = "#fff" if primary else "var(--ink)"
    return f'<g class="{cls}">{box(x, y, w, h, f, "var(--brand)" if primary else "var(--line)", 8)}{txt(x + w / 2, y + h / 2 + 4, label, 11, 700, c, "middle")}</g>'

def ring(x, y, w, h, n, cls):
    """anel de destaque + numero (aparece junto do clique)"""
    return (f'<g class="{cls}"><rect x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="11" fill="none" stroke="var(--brand)" stroke-width="2.5"/>'
            f'<circle cx="{x + w + 3}" cy="{y - 3}" r="9" fill="var(--brand)"/><text x="{x + w + 3}" y="{y + 0.5}" font-size="11" font-weight="800" fill="#fff" text-anchor="middle">{n}</text></g>')

def field(x, y, w, label, grow, val_w):
    return (txt(x, y, label, 10, 600, "var(--mut)") + box(x, y + 4, w, 22, "var(--bg)", "var(--line)", 6)
            + f'<rect class="{grow}" x="{x + 6}" y="{y + 11}" width="{val_w}" height="8" rx="4" fill="var(--mut)" opacity=".55"/>')

def frame(inner, active=None, title="", nav=True):
    """ecra de telemovel: barra de topo + conteudo + barra de baixo"""
    o = ['<rect width="360" height="300" fill="var(--bg)"/>', '<rect width="360" height="34" fill="var(--sf)"/><path d="M0 34h360" stroke="var(--line)"/>',
         '<rect x="12" y="8" width="18" height="18" rx="5" fill="var(--brand)"/><rect x="16" y="13" width="10" height="2.4" rx="1.2" fill="#f5a524"/><rect x="16" y="17" width="7" height="2.4" rx="1.2" fill="#5b7cff"/><rect x="18" y="21" width="8" height="2.4" rx="1.2" fill="#22a06b"/>',
         txt(38, 22, "Claquete", 13, 700), f'<circle cx="338" cy="17" r="11" fill="var(--brand)"/>' + txt(338, 21, "D", 11, 700, "#fff", "middle")]
    o.append(inner)
    if nav:
        o.append('<rect y="252" width="360" height="48" fill="var(--sf)"/><path d="M0 252h360" stroke="var(--line)"/>')
        for k, n in enumerate(NAV):
            x = 30 + 60 * k; on = (active == k); col = "var(--brand)" if on else "var(--mut)"
            if on: o.append(f'<rect x="{x - 27}" y="256" width="54" height="40" rx="10" fill="var(--brand)" opacity=".12"/>')
            o.append(f'<g transform="translate({x} 268)" fill="none" stroke="{col}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICON[k]}</g>' + txt(x, 289, n, 8.5, 700 if on else 500, col, "middle"))
    return "".join(o)

def svg(inner, label, extra_cls=""):
    return f'<svg class="an {extra_cls}" viewBox="0 0 360 300" role="img" aria-label="{label}">{inner}</svg>'

def navpt(k): return (30 + 60 * k, 276)
def navring(k, n, cls): return ring(30 + 60 * k - 27, 256, 54, 40, n, cls)

def tiles(y=48):
    o = ""
    for i, (c, l) in enumerate((("#f5a524", "Por faturar"), ("#5b7cff", "Por receber"), ("var(--brand)", "Faturado"), ("#22a06b", "Recebido"))):
        x = 12 + (i % 2) * 170; yy = y + (i // 2) * 62
        o += box(x, yy, 164, 54, "var(--sf)") + f'<rect x="{x}" y="{yy}" width="4" height="54" rx="2" fill="{c}"/>' + txt(x + 14, yy + 20, l, 10, 600, "var(--mut)") + f'<rect x="{x + 14}" y="{yy + 29}" width="{50 + i * 14}" height="10" rx="5" fill="var(--ink)" opacity=".75"/>'
    return o

def rows3(y=84):
    return "".join(box(12, y + i * 40, 336, 34, "var(--sf)") + f'<circle cx="30" cy="{y + 17 + i * 40}" r="9" fill="var(--brand)" opacity=".18"/><rect x="48" y="{y + 11 + i * 40}" width="{110 - i * 14}" height="8" rx="4" fill="var(--ink)" opacity=".7"/><rect x="48" y="{y + 23 + i * 40}" width="{70 + i * 10}" height="6" rx="3" fill="var(--mut)" opacity=".5"/>' for i in range(3))

# ------------------------------------------------------------------ cenas
def s_clientes():
    L = "Escolher o separador Clientes"
    base = frame(f'<g class="g1">{tiles()}</g>', 0)
    lst = f'<g class="s1">{frame("", 3)}{txt(16, 58, "Clientes", 16, 700)}{btn(236, 42, 108, 26, "Novo cliente", "")}{rows3(84)}</g>'
    form = (f'<g class="s2"><rect width="360" height="252" y="34" fill="#000" opacity=".25"/>{box(16, 76, 328, 156, "var(--sf)", "var(--line)", 12)}{txt(30, 98, "Novo cliente", 13, 700)}'
            + field(30, 112, 150, "Nome", "wb", 90) + field(190, 112, 140, "NIF", "wb2", 60) + field(30, 152, 150, "Contacto", "wb3", 100) + btn(246, 196, 84, 26, "Guardar") + '</g>')
    done = f'<g class="s3"><circle cx="180" cy="160" r="30" fill="#22a06b"/><path d="M165 160l11 11 21-22" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>'
    rings = navring(3, 1, "h1") + ring(236, 42, 108, 26, 2, "h2") + ring(246, 196, 84, 26, 3, "h3")
    return svg(base + lst + form + rings + done + cur([(180, 215), navpt(3), (290, 56), (288, 212)]), "Clientes")

def s_eventos():
    cells = ""
    for r in range(4):
        for c in range(7):
            n = r * 7 + c + 1
            if n > 30: continue
            cells += box(12 + c * 48, 70 + r * 40, 44, 36, "var(--sf)", "var(--line)", 6) + txt(18 + c * 48, 84 + r * 40, n, 9, 600, "var(--mut)")
    cal = frame(f'{txt(16, 58, "Calendário", 16, 700)}{cells}', 1)
    form = (f'<g class="s1"><rect width="360" height="218" y="34" fill="var(--bg)"/>{txt(16, 58, "Novo evento", 16, 700)}'
            + field(16, 72, 200, "Cliente", "wa", 110) + field(226, 72, 118, "Datas", "wa2", 70)
            + field(16, 112, 140, "Valor", "wa3", 50) + f'<g class="pf">{field(170, 112, 174, "Data da fatura ★", "wb", 90)}</g>'
            + f'{txt(170, 158, "★ " + "Estatísticas", 9, 700, "var(--brand)")}{btn(250, 190, 94, 28, "Guardar")}</g>')
    saved = f'<g class="s3">{box(36, 96, 288, 70, "var(--sf)", "#22a06b", 12)}<circle cx="68" cy="131" r="16" fill="#22a06b"/><path d="M60 131l6 6 11-12" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>{txt(96, 128, "Novo evento", 13, 700)}<rect x="96" y="138" width="130" height="7" rx="3.5" fill="var(--mut)" opacity=".5"/></g>'
    rings = ring(12 + 2 * 48, 70 + 1 * 40, 44, 36, 1, "h1") + ring(170, 116, 174, 26, 2, "h2") + ring(250, 190, 94, 28, 3, "h3")
    return svg(cal + f'<g class="x3">{form}</g>' if False else cal + form + saved + rings + cur([(300, 230), (122, 124), (255, 133), (297, 204)]), "Eventos")

def s_stats():
    bars = "".join(f'<rect class="gr" x="{26 + i * 26}" y="{210 - h}" width="16" height="{h}" rx="4" fill="var(--brand)" opacity="{.35 + .05 * (i % 5)}" style="animation-delay:{i * .05}s"/>' for i, h in enumerate((40, 64, 52, 90, 76, 110, 98, 132, 120, 86, 104, 140)))
    chart = f'<g class="s1">{frame("", 5)}{txt(16, 58, "Estatísticas", 16, 700)}{box(12, 70, 336, 168, "var(--sf)")}{bars}<g class="s2">{box(150, 84, 66, 26, "var(--ink)", "var(--ink)", 7)}{txt(183, 101, "1 234 €", 11, 700, "var(--bg)", "middle")}</g></g>'
    home = f'<g class="g1">{frame(tiles(), 0)}</g>'
    rings = navring(5, 1, "h1") + ring(120, 110, 18, 100, 2, "h2") + navring(0, 3, "h3")
    return svg(home + chart + rings + cur([(180, 215), navpt(5), (130, 160), navpt(0)]), "Estatísticas")

def s_chat():
    base = frame(f'{tiles()}', 0)
    lst = (f'<g class="s1">{frame("", 4)}{txt(16, 56, "Chat", 16, 700)}'
           f'{box(12, 64, 336, 26, "var(--bg)", "var(--line)", 13)}<rect x="20" y="75" width="40" height="5" rx="2.5" fill="var(--mut)" opacity=".5"/>'
           f'<g><rect x="12" y="98" width="108" height="24" rx="8" fill="var(--brand)" opacity=".15"/>{txt(66, 114, "Conversas", 10, 700, "var(--brand)", "middle")}{txt(180, 114, "Contactos", 10, 600, "var(--mut)", "middle")}{txt(294, 114, "Grupos", 10, 600, "var(--mut)", "middle")}</g></g>')
    ct = (f'<g class="s2">{box(0, 98, 360, 154, "var(--bg)", "var(--bg)", 0)}<rect x="12" y="98" width="108" height="24" rx="8" fill="none"/><rect x="126" y="98" width="108" height="24" rx="8" fill="var(--brand)" opacity=".15"/>{txt(180, 114, "Contactos", 10, 700, "var(--brand)", "middle")}'
          f'{txt(66, 114, "Conversas", 10, 600, "var(--mut)", "middle")}{txt(294, 114, "Grupos", 10, 600, "var(--mut)", "middle")}'
          f'{box(12, 134, 262, 30, "var(--sf)")}<rect class="wb" x="22" y="146" width="150" height="7" rx="3.5" fill="var(--mut)" opacity=".6"/>{btn(280, 134, 68, 30, "Adicionar")}</g>')
    done = (f'<g class="s3">{box(12, 176, 336, 52, "var(--sf)")}<circle cx="40" cy="202" r="15" fill="#e6893c"/><circle cx="40" cy="202" r="18" fill="none" stroke="#22a06b" stroke-width="3.5"/>{txt(40, 207, "A", 13, 700, "#fff", "middle")}'
            f'<rect x="68" y="192" width="90" height="8" rx="4" fill="var(--ink)" opacity=".7"/><rect x="68" y="207" width="60" height="6" rx="3" fill="#22a06b" opacity=".7"/>'
            f'<g><rect x="230" y="190" width="100" height="26" rx="10" fill="var(--brand)"/>{txt(280, 207, "😊 👍", 12, 500, "#fff", "middle")}</g></g>')
    rings = navring(4, 1, "h1") + ring(126, 98, 108, 24, 2, "h2") + ring(280, 134, 68, 30, 3, "h3")
    return svg(base + lst + ct + done + rings + cur([(200, 215), navpt(4), (180, 112), (314, 152)]), "Chat")

def phone(x, label):
    return f'<g transform="translate({x} 18)">{box(0, 0, 150, 262, "var(--sf)", "var(--ink)", 20)}{box(7, 18, 136, 226, "var(--bg)", "var(--line)", 10)}<rect x="55" y="6" width="40" height="5" rx="2.5" fill="var(--ink)" opacity=".5"/>{txt(75, 258, label, 9, 700, "var(--mut)", "middle")}</g>'

def s_install():
    a = phone(20, "Android"); i = phone(190, "iPhone")
    a_menu = f'<g class="s1">{box(70, 60, 78, 52, "var(--sf)", "var(--line)", 8)}{txt(80, 80, "Instalar app", 9, 700)}<rect x="80" y="92" width="48" height="5" rx="2.5" fill="var(--mut)" opacity=".5"/></g>'
    a_icon = '<g class="s2"><rect x="38" y="190" width="30" height="30" rx="8" fill="var(--brand)"/><rect x="45" y="197" width="16" height="3.4" rx="1.7" fill="#f5a524"/><rect x="45" y="203" width="11" height="3.4" rx="1.7" fill="#5b7cff"/><rect x="47" y="209" width="13" height="3.4" rx="1.7" fill="#22a06b"/></g>'
    dots = '<g fill="var(--mut)"><circle cx="150" cy="40" r="1.8"/><circle cx="150" cy="46" r="1.8"/><circle cx="150" cy="52" r="1.8"/></g>'
    shr = '<g transform="translate(265 226)" fill="none" stroke="var(--brand)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M0 4v-12M-4 -4l4 -4 4 4M-6 0v9h12v-9"/></g>'
    i_sheet = f'<g class="s3">{box(197, 150, 136, 90, "var(--sf)", "var(--line)", 10)}{txt(265, 172, "Adicionar ao ecrã principal", 7.6, 700, "var(--ink)", "middle")}<rect x="250" y="184" width="30" height="30" rx="8" fill="var(--brand)"/><rect x="257" y="191" width="16" height="3.4" rx="1.7" fill="#f5a524"/><rect x="257" y="197" width="11" height="3.4" rx="1.7" fill="#5b7cff"/><rect x="259" y="203" width="13" height="3.4" rx="1.7" fill="#22a06b"/></g>'
    rings = ring(133, 50, 22, 24, 1, "h1") + ring(76, 70, 70, 24, 2, "h2") + ring(251, 214, 28, 28, 3, "h3")
    return svg(a + i + dots + shr + a_menu + a_icon + i_sheet + rings + cur([(180, 280), (143, 62), (100, 86), (265, 226)]), "Android e iPhone")

def s_suporte():
    foot = (f'<g class="g1">{frame(tiles(), 0)}<g>{txt(110, 232, "Suporte", 11, 700, "var(--brand)", "middle")}{txt(180, 232, "·", 11, 700, "var(--mut)", "middle")}{txt(240, 232, "Sobre", 11, 600, "var(--mut)", "middle")}</g></g>')
    form = (f'<g class="s1">{frame("", 0)}{txt(16, 58, "Suporte", 16, 700)}{box(12, 70, 336, 80, "var(--sf)")}<rect class="wa" x="24" y="84" width="240" height="7" rx="3.5" fill="var(--mut)" opacity=".6"/><rect class="wa2" x="24" y="98" width="180" height="7" rx="3.5" fill="var(--mut)" opacity=".6"/>'
            f'{btn(262, 160, 86, 28, "Enviar")}</g>')
    sent = f'<g class="s2">{box(110, 196, 238, 28, "var(--brand)", "var(--brand)", 12)}{txt(229, 214, "✓", 12, 700, "#fff", "middle")}</g>'
    rep = f'<g class="s3">{box(12, 160, 250, 34, "var(--sf)", "var(--line)", 12)}{txt(24, 181, "💬", 13)}<rect x="48" y="172" width="150" height="7" rx="3.5" fill="var(--ink)" opacity=".6"/><rect x="48" y="184" width="100" height="5" rx="2.5" fill="var(--mut)" opacity=".5"/></g>'
    rings = ring(88, 218, 44, 20, 1, "h1") + ring(262, 160, 86, 28, 2, "h2") + ring(12, 160, 250, 34, 3, "h3")
    return svg(foot + form + sent + rep + rings + cur([(250, 130), (110, 230), (305, 174), (130, 178)]), "Suporte")

def s_conta():
    home = f'<g class="g1">{frame(tiles(), 0)}{txt(12, 234, "dan", 11, 700, "var(--brand)")}</g>'
    sett = (f'<g class="s1">{frame("", 0)}{box(12, 46, 336, 92, "var(--sf)")}{txt(24, 66, "Foto de perfil", 12, 700)}<circle cx="54" cy="102" r="24" fill="var(--bg)" stroke="var(--line)"/>{txt(54, 108, "D", 18, 700, "var(--mut)", "middle")}'
            f'<g class="s2"><circle cx="54" cy="102" r="24" fill="#e6893c"/><circle cx="54" cy="96" r="8" fill="#ffdcb8"/><path d="M38 118c3-10 13-10 16-10s13 0 16 10a24 24 0 0 1-32 0z" fill="#3b4cdb"/></g>'
            f'{btn(96, 90, 110, 26, "Escolher imagem", "", False)}'
            f'{box(12, 146, 336, 98, "var(--sf)")}{txt(24, 166, "Alterar palavra-passe", 12, 700)}<rect x="24" y="178" width="170" height="20" rx="6" fill="var(--bg)" stroke="var(--line)"/><rect class="wb" x="30" y="185" width="80" height="7" rx="3.5" fill="var(--mut)" opacity=".6"/>{btn(250, 206, 86, 26, "Guardar")}</g>')
    ok = '<g class="s3"><circle cx="300" cy="160" r="18" fill="#22a06b"/><path d="M291 160l6 6 12-13" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/></g>'
    rings = ring(8, 216, 44, 26, 1, "h1") + ring(96, 90, 110, 26, 2, "h2") + ring(250, 206, 86, 26, 3, "h3")
    return svg(home + sett + ok + rings + cur([(200, 140), (30, 232), (150, 104), (293, 220)]), "Conta")

def s_gcal():
    cl = (f'{frame("", 0, nav=False)}{box(12, 46, 336, 60, "var(--sf)")}{txt(24, 66, "Google Calendar", 12, 700)}<rect x="24" y="76" width="236" height="22" rx="6" fill="var(--bg)" stroke="var(--line)"/>'
          f'<text x="32" y="91" font-size="9" fill="var(--mut)">…/calendar.ics</text>{btn(268, 76, 66, 22, "Copiar", "", False)}')
    g = (f'<g class="s1">{box(12, 118, 336, 118, "var(--sf)", "#4285f4", 10)}{txt(24, 138, "Google Calendar", 11, 700, "#4285f4")}{txt(24, 158, "Outras agendas", 10, 600, "var(--ink)")}{txt(24, 178, "A partir do URL", 10, 600, "var(--ink)")}'
         f'<rect x="24" y="188" width="200" height="22" rx="6" fill="var(--bg)" stroke="var(--line)"/><rect class="wb" x="30" y="195" width="140" height="7" rx="3.5" fill="var(--mut)" opacity=".6"/></g>')
    wait = (f'<g class="s3"><rect x="12" y="118" width="336" height="118" rx="10" fill="var(--sf)" stroke="#4285f4"/>'
            f'<g transform="translate(60 177)"><circle r="22" fill="none" stroke="var(--mut)" stroke-width="3"/><path class="hand" d="M0 0V-14" stroke="var(--brand)" stroke-width="3.4" stroke-linecap="round"/><path d="M0 0l9 5" stroke="var(--mut)" stroke-width="3" stroke-linecap="round"/></g>'
            f'{txt(100, 176, "⏳ Pode demorar horas", 11, 700)}<rect x="100" y="196" width="150" height="20" rx="6" fill="#22a06b" opacity=".85"/>{txt(175, 210, "✓ Novo evento", 10, 700, "#fff", "middle")}</g>')
    rings = ring(268, 76, 66, 22, 1, "h1") + ring(24, 168, 100, 16, 2, "h2") + ring(24, 188, 200, 22, 3, "h3")
    return svg(cl + g + wait + rings + cur([(200, 270), (300, 90), (70, 176), (120, 202)]), "Google Calendar")

def s_idiomas():
    chips = "".join(f'<g>{box(40 + i * 56, 214, 48, 24, "var(--sf)", "var(--line)", 12)}{txt(64 + i * 56, 230, l, 11, 700, "var(--mut)", "middle")}</g>' for i, l in enumerate(("PT", "EN", "ES", "FR", "IT")))
    t = lambda cls, s, sub: f'<g class="{cls}">{txt(180, 130, s, 22, 800, "var(--brand)", "middle")}{txt(180, 156, sub, 12, 500, "var(--mut)", "middle")}</g>'
    body = (frame(f'{chips}', 0, nav=False) + t("g1", "Bem-vindo!", "Português") + t("v1", "Welcome!", "English") + t("v2", "¡Bienvenido!", "Español") + t("v3", "Bienvenue !", "Français"))
    sel = lambda i, cls: f'<g class="{cls}"><rect x="{40 + i * 56}" y="214" width="48" height="24" rx="12" fill="var(--brand)"/>{txt(64 + i * 56, 230, ("PT", "EN", "ES", "FR", "IT")[i], 11, 700, "#fff", "middle")}</g>'
    rings = ring(40 + 56, 214, 48, 24, 1, "h1") + ring(40 + 112, 214, 48, 24, 2, "h2") + ring(40 + 168, 214, 48, 24, 3, "h3")
    return svg(body + sel(1, "v1") + sel(2, "v2") + sel(3, "v3") + rings + cur([(180, 190), (120, 228), (176, 228), (232, 228)]), "Idiomas")

def s_autor():
    flag = '<g transform="translate(130 80)" class="s1"><rect width="100" height="66" rx="8" fill="#e42518"/><rect width="40" height="66" rx="8" fill="#0b7a3b"/><rect x="30" width="10" height="66" fill="#0b7a3b"/><circle cx="40" cy="33" r="11" fill="#fbd600" stroke="#fff" stroke-width="2"/></g>'
    heart = '<g class="s2 beat" transform="translate(180 190)"><path d="M0 14c-14-9-20-17-20-25a10 10 0 0 1 20-3 10 10 0 0 1 20 3c0 8-6 16-20 25z" fill="#e5484d"/></g>'
    ppl = "".join(f'<g class="s3"><circle cx="{60 + i * 48}" cy="262" r="7" fill="var(--brand)" opacity=".8"/><path d="M{49 + i * 48} 282c0-8 5-10 11-10s11 2 11 10z" fill="var(--brand)" opacity=".8"/></g>' for i in range(6))
    return svg(frame(txt(180, 62, "Daniel Nunes", 15, 800, "var(--ink)", "middle") + txt(180, 232, "Made in Portugal", 11, 700, "var(--mut)", "middle"), None, nav=False) + flag + heart + ppl, "Made in Portugal", "nocur")

SCENES = [s_clientes, s_eventos, s_stats, s_chat, s_install, s_suporte, s_conta, s_gcal, s_idiomas, s_autor]

CSS = """
.an{display:block;width:100%;max-width:520px;height:auto;margin:0 auto 14px;border-radius:16px;border:1px solid var(--line);background:var(--bg);box-shadow:0 6px 24px #0000001a}
.an .cur{animation:cur 10s linear infinite;transform:translate(var(--x0),var(--y0));pointer-events:none}.an.nocur .cur{display:none}
.an .rip{fill:var(--brand);opacity:0;transform-box:fill-box;transform-origin:center;animation:rip 10s linear infinite}
.an .h1,.an .h2,.an .h3,.an .s1,.an .s2,.an .s3,.an .v1,.an .v2,.an .v3{opacity:0}.an .g1{animation:g1 10s infinite}
.an .h1{animation:h1 10s infinite}.an .h2{animation:h2 10s infinite}.an .h3{animation:h3 10s infinite}
.an .s1{animation:s1 10s infinite}.an .s2{animation:s2 10s infinite}.an .s3{animation:s3 10s infinite}
.an .v1{animation:v1 10s infinite}.an .v2{animation:v2 10s infinite}.an .v3{animation:v3 10s infinite}
.an .wa,.an .wa2,.an .wa3,.an .wb,.an .wb2,.an .wb3{transform-box:fill-box;transform-origin:left center;transform:scaleX(0)}
.an .wa{animation:wa 10s infinite}.an .wa2{animation:wa 10s .25s infinite}.an .wa3{animation:wa 10s .5s infinite}.an .wb{animation:wb 10s infinite}.an .wb2{animation:wb 10s .25s infinite}.an .wb3{animation:wb 10s .5s infinite}
.an .gr{transform-box:fill-box;transform-origin:bottom center;animation:gr 10s infinite}.an .beat{animation:s2 10s infinite}.an .hand{transform-origin:0 0;animation:spin 2s linear infinite}
@keyframes cur{0%{transform:translate(var(--x0),var(--y0))}12%,26%{transform:translate(var(--x1),var(--y1))}38%,54%{transform:translate(var(--x2),var(--y2))}66%,82%{transform:translate(var(--x3),var(--y3))}94%,100%{transform:translate(var(--x0),var(--y0))}}
@keyframes rip{0%,16%{opacity:0;transform:scale(.3)}18%{opacity:.55}27%{opacity:0;transform:scale(1.8)}27.1%,44%{opacity:0;transform:scale(.3)}46%{opacity:.55}55%{opacity:0;transform:scale(1.8)}55.1%,72%{opacity:0;transform:scale(.3)}74%{opacity:.55}83%,100%{opacity:0;transform:scale(1.8)}}
@keyframes h1{0%,8%{opacity:0}12%,28%{opacity:1}32%,100%{opacity:0}}@keyframes h2{0%,36%{opacity:0}40%,56%{opacity:1}60%,100%{opacity:0}}@keyframes h3{0%,64%{opacity:0}68%,84%{opacity:1}88%,100%{opacity:0}}
@keyframes s1{0%,27%{opacity:0}31%,94%{opacity:1}98%,100%{opacity:0}}@keyframes s2{0%,55%{opacity:0}59%,94%{opacity:1}98%,100%{opacity:0}}@keyframes s3{0%,83%{opacity:0}87%,94%{opacity:1}98%,100%{opacity:0}}
@keyframes g1{0%,27%{opacity:1}31%,94%{opacity:0}98%,100%{opacity:1}}
@keyframes v1{0%,27%{opacity:0}31%,52%{opacity:1}56%,100%{opacity:0}}@keyframes v2{0%,55%{opacity:0}59%,78%{opacity:1}82%,100%{opacity:0}}@keyframes v3{0%,83%{opacity:0}87%,94%{opacity:1}98%,100%{opacity:0}}
@keyframes wa{0%,27%{transform:scaleX(0)}40%,94%{transform:scaleX(1)}98%,100%{transform:scaleX(0)}}@keyframes wb{0%,55%{transform:scaleX(0)}68%,94%{transform:scaleX(1)}98%,100%{transform:scaleX(0)}}
@keyframes gr{0%,27%{transform:scaleY(0)}45%,94%{transform:scaleY(1)}98%,100%{transform:scaleY(0)}}@keyframes spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.an *{animation:none!important}.an .s1,.an .h1{opacity:1}.an .g1,.an .cur,.an .rip,.an .h2,.an .h3,.an .s2,.an .s3,.an .v1,.an .v2,.an .v3{display:none}.an .wa,.an .wa2,.an .wa3,.an .wb,.an .wb2,.an .wb3,.an .gr{transform:none}}
"""
