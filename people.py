"""Rede de freelancers AV: listas de funções, sugestões, pesquisa e traduções."""
import unicodedata

# (grupo, [(chave, pt, en, es, fr, it)])
GROUPS = [
    (("Imagem e realização", "Image and directing", "Imagen y realización", "Image et réalisation", "Immagine e regia"), [
        ("cam", "Operador de câmara", "Camera operator", "Operador de cámara", "Cadreur", "Operatore di camera"),
        ("dir", "Realizador", "Director", "Realizador", "Réalisateur", "Regista"),
        ("dop", "Diretor de fotografia", "Director of photography", "Director de fotografía", "Directeur de la photographie", "Direttore della fotografia"),
        ("ad", "Assistente de realização", "Assistant director", "Ayudante de dirección", "Assistant réalisateur", "Assistente alla regia"),
        ("ac", "Assistente de câmara / focus puller", "Camera assistant / focus puller", "Ayudante de cámara / foquista", "Assistant caméra / pointeur", "Assistente operatore / fuochista"),
        ("steadi", "Steadicam / gimbal", "Steadicam / gimbal", "Steadicam / gimbal", "Steadicam / gimbal", "Steadicam / gimbal"),
        ("jib", "Operador de grua / jib", "Crane / jib operator", "Operador de grúa / jib", "Opérateur grue / jib", "Operatore gru / jib"),
        ("drone", "Piloto de drone", "Drone pilot", "Piloto de dron", "Pilote de drone", "Pilota di droni"),
        ("photo", "Fotógrafo", "Photographer", "Fotógrafo", "Photographe", "Fotografo"),
        ("dit", "DIT / gestão de dados", "DIT / data management", "DIT / gestión de datos", "DIT / gestion des données", "DIT / gestione dati"),
        ("tele", "Operador de teleponto", "Teleprompter operator", "Operador de teleprompter", "Opérateur prompteur", "Operatore teleprompter"),
    ]),
    (("Vídeo e transmissão", "Video and broadcast", "Vídeo y emisión", "Vidéo et diffusion", "Video e broadcast"), [
        ("vtec", "Técnico de vídeo", "Video technician", "Técnico de vídeo", "Technicien vidéo", "Tecnico video"),
        ("vop", "Operador de vídeo / mesa de misturas", "Video operator / vision mixer", "Operador de vídeo / mezclador", "Opérateur vidéo / mélangeur", "Operatore video / mixer"),
        ("led", "Técnico de ecrãs LED / projeção", "LED screen / projection technician", "Técnico de pantallas LED / proyección", "Technicien écrans LED / projection", "Tecnico schermi LED / proiezione"),
        ("media", "Operador de media server", "Media server operator", "Operador de media server", "Opérateur media server", "Operatore media server"),
        ("pb", "Operador de playback", "Playback operator", "Operador de playback", "Opérateur playback", "Operatore playback"),
        ("stream", "Técnico de streaming", "Streaming technician", "Técnico de streaming", "Technicien streaming", "Tecnico streaming"),
        ("regie", "Técnico de régie / broadcast", "Broadcast / control room technician", "Técnico de realización / broadcast", "Technicien régie / broadcast", "Tecnico regia / broadcast"),
        ("map", "Video mapping", "Video mapping", "Video mapping", "Video mapping", "Video mapping"),
    ]),
    (("Luz", "Lighting", "Iluminación", "Lumière", "Luci"), [
        ("ltec", "Técnico de iluminação", "Lighting technician", "Técnico de iluminación", "Technicien lumière", "Tecnico luci"),
        ("lop", "Operador de mesa de luz", "Lighting console operator", "Operador de mesa de luces", "Opérateur console lumière", "Operatore console luci"),
        ("ldes", "Desenhador de luz", "Lighting designer", "Diseñador de iluminación", "Concepteur lumière", "Lighting designer"),
        ("gaf", "Gaffer / eletricista de cinema", "Gaffer / film electrician", "Gaffer / eléctrico de cine", "Chef électricien", "Gaffer / elettricista di scena"),
    ]),
    (("Som", "Sound", "Sonido", "Son", "Audio"), [
        ("stec", "Técnico de som", "Sound technician", "Técnico de sonido", "Technicien son", "Tecnico audio"),
        ("foh", "Técnico de FOH / PA", "FOH / PA engineer", "Técnico de FOH / PA", "Ingénieur FOH / PA", "Tecnico FOH / PA"),
        ("mon", "Técnico de monitores", "Monitor engineer", "Técnico de monitores", "Ingénieur retours", "Tecnico monitor"),
        ("bs", "Operador de boom / som direto", "Boom operator / location sound", "Operador de jirafa / sonido directo", "Perchman / ingénieur du son", "Microfonista / presa diretta"),
        ("rf", "Técnico de rádio frequência (RF)", "RF technician", "Técnico de radiofrecuencia (RF)", "Technicien radiofréquence (RF)", "Tecnico radiofrequenza (RF)"),
    ]),
    (("Palco e produção", "Stage and production", "Escenario y producción", "Scène et production", "Palco e produzione"), [
        ("stage", "Stagehand / técnico de palco", "Stagehand", "Tramoyista / técnico de escenario", "Machiniste / technicien plateau", "Macchinista / tecnico di palco"),
        ("rig", "Rigger", "Rigger", "Rigger", "Rigger", "Rigger"),
        ("sm", "Stage manager / diretor de palco", "Stage manager", "Regidor / director de escena", "Régisseur de scène", "Stage manager"),
        ("prod", "Produtor / diretor de produção", "Producer / production manager", "Productor / director de producción", "Producteur / directeur de production", "Produttore / direttore di produzione"),
        ("pa", "Assistente de produção", "Production assistant", "Ayudante de producción", "Assistant de production", "Assistente di produzione"),
        ("tm", "Diretor técnico", "Technical director", "Director técnico", "Directeur technique", "Direttore tecnico"),
    ]),
    (("Pós-produção", "Post-production", "Posproducción", "Post-production", "Post-produzione"), [
        ("edit", "Editor de vídeo", "Video editor", "Editor de vídeo", "Monteur", "Montatore"),
        ("col", "Colorista", "Colorist", "Colorista", "Étalonneur", "Color grader"),
        ("mot", "Motion designer / VFX", "Motion designer / VFX", "Motion designer / VFX", "Motion designer / VFX", "Motion designer / VFX"),
        ("sd", "Pós-produção de som / mistura", "Sound post-production / mixing", "Posproducción de sonido / mezcla", "Post-production son / mixage", "Post-produzione audio / mix"),
    ]),
]
ROLES = {k: (g[0], r[1:]) for g in GROUPS for r in g[1] for k in [r[0]]}

TRAVEL = [("no", "Só na minha zona", "Only in my area", "Solo en mi zona", "Seulement dans ma région", "Solo nella mia zona"),
          ("pt", "Disponível a viajar no meu país", "Available to travel in my country", "Disponible para viajar por mi país", "Disponible pour voyager dans mon pays", "Disponibile a viaggiare nel mio paese"),
          ("eu", "Disponível a viajar na Europa", "Available to travel in Europe", "Disponible para viajar por Europa", "Disponible pour voyager en Europe", "Disponibile a viaggiare in Europa"),
          ("world", "Disponível a viajar para qualquer lado", "Available to travel anywhere", "Disponible para viajar a cualquier lugar", "Disponible pour voyager partout", "Disponibile a viaggiare ovunque")]
TRAVEL_D = {t[0]: t[1] for t in TRAVEL}

SOFT = ["grandMA3", "grandMA2", "Hog 4", "ChamSys MagicQ", "Avolites Titan", "Capture", "WYSIWYG", "Vectorworks", "Resolume", "Disguise", "Watchout", "vMix", "OBS", "ATEM", "QLab", "TouchDesigner",
        "Premiere Pro", "DaVinci Resolve", "After Effects", "Final Cut", "Avid Media Composer", "Pro Tools", "Ableton Live", "Dante", "Smaart", "Reaper"]
GEAR = ["Sony FX6", "Sony FX9", "Sony FX3", "Blackmagic URSA", "ARRI Alexa", "RED", "Canon C70", "Panasonic AK-UC", "DJI Ronin", "DJI Mavic", "Barco E2", "Analog Way", "Christie", "Yamaha CL/QL",
        "DiGiCo", "Midas", "Allen & Heath", "Shure Axient", "Robe", "Martin", "Clay Paky", "ETC", "L-Acoustics", "d&b", "LED wall", "Mesa de corte ATEM", "Grua / jib", "Steadicam"]

def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))

def haystack(p):
    parts = [p["headline"], p["roles_other"], p["software"], p["gear"], p["career"], p["companies"], p["projects"], p["city"]]
    for k in (p["roles"] or "").split(","):
        if k in ROLES: parts += list(ROLES[k][1])
    return norm(" ".join(x or "" for x in parts))

def match(p, q):
    h = haystack(p)
    return all(w in h for w in norm(q).split())

def csv(s, n=40):
    return [x.strip() for x in (s or "").replace("\n", ",").split(",") if x.strip()][:n]

def _rows():
    out = []
    for g in GROUPS:
        out.append(g[0]); out += [r[1:] for r in g[1]]
    out += [t[1:] for t in TRAVEL]
    return out
ROWS = _rows()

CSS = """
.pf{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));margin-bottom:18px}
.pc{display:flex;gap:12px;padding:14px;background:var(--sf);border:1px solid var(--line);border-radius:var(--r);text-decoration:none;color:inherit}
.pc:hover{border-color:var(--brand)}.pc .avw{flex:none;width:48px;height:48px}.pc .av{width:48px;height:48px;font-size:1.05rem}.pc b{display:block}.pc small{color:var(--mut);display:block}
.tg2{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}.tg2 i,.tgs span{font-style:normal;font-size:.75rem;padding:2px 9px;border-radius:99px;background:color-mix(in srgb,var(--brand) 12%,transparent);color:var(--brand);font-weight:600}
.tgs{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}.tgs span.n{background:var(--line);color:var(--ink);font-weight:500}
.fl{display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-bottom:16px}.fl>div{flex:1;min-width:150px}.fl label{margin-top:0}
.rg{margin-bottom:12px}.rg h3{font-size:.85rem;color:var(--mut);margin:12px 0 6px}.rg .ck{display:flex;gap:6px 14px;flex-wrap:wrap}.rg label.c{margin:0;font-weight:500}
.pp{display:flex;gap:16px;align-items:center;margin-bottom:12px}.pp .av{width:76px;height:76px;font-size:1.6rem}.pp h1{margin:0}
.sg{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 12px}.sg button{font-size:.76rem;padding:3px 10px;border-radius:99px}
.pv{white-space:pre-wrap;line-height:1.55}.nl .sm{display:none}
@media(max-width:820px){.nl .lg{display:none}.nl .sm{display:inline}}
"""
