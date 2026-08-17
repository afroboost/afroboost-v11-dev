# -*- coding: utf-8 -*-
"""V445 — la petite icone de notification Android n'est plus un carre blanc.

Tout est hors ligne : aucun reseau, aucune base, AUCUNE notification envoyee.
Le PNG est decode et re-encode en Python pur (ni Pillow, ni dependance).

Lancement :  python3 tests/test_v445_icone_notification.py
"""
import io, os, re, struct, sys, zlib

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(RACINE, "frontend", "public")
BADGE = os.path.join(PUB, "notification-badge-96.png")
SOURCE = os.path.join(PUB, "logo512.png")
SW = os.path.join(PUB, "sw.js")

RESULTATS = []
def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# --------------------------------------------------------------- PNG, en pur Python
def png_decode(p):
    d = open(p, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    i, idat, ihdr = 8, b"", None
    while i < len(d):
        ln = struct.unpack(">I", d[i:i+4])[0]; t = d[i+4:i+8]
        dat = d[i+8:i+8+ln]; i += 12 + ln
        if t == b"IHDR": ihdr = dat
        elif t == b"IDAT": idat += dat
        elif t == b"IEND": break
    w, h, bd, ct, _, _, inter = struct.unpack(">IIBBBBB", ihdr)
    nc = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    if bd != 8 or inter: return w, h, ct, nc, None
    raw = zlib.decompress(idat); stride = w * nc
    lignes, prev, pos = [], bytearray(stride), 0
    for _y in range(h):
        f = raw[pos]; pos += 1
        cur = bytearray(raw[pos:pos+stride]); pos += stride
        for x in range(stride):
            a = cur[x-nc] if x >= nc else 0
            b = prev[x]; c = prev[x-nc] if x >= nc else 0
            if f == 1: cur[x] = (cur[x]+a) & 255
            elif f == 2: cur[x] = (cur[x]+b) & 255
            elif f == 3: cur[x] = (cur[x]+(a+b)//2) & 255
            elif f == 4:
                pa, pb, pc = abs(b-c), abs(a-c), abs(a+b-2*c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[x] = (cur[x]+pr) & 255
        lignes.append(bytes(cur)); prev = cur
    return w, h, ct, nc, lignes


def png_encode(w, h, px):
    raw = b"".join(b"\x00" + bytes(r) for r in px)
    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t+d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"
            + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))


def deriver_silhouette(src, taille=96, seuil=30, marge=0.10):
    """LA recette du badge livre. Elle EXTRAIT la forme de l'asset officiel :
    tout ce qui n'est pas le fond noir devient opaque, le reste transparent."""
    w, h, ct, nc, rows = png_decode(src)
    lum = [[(rows[y][x*nc]*299 + rows[y][x*nc+1]*587 + rows[y][x*nc+2]*114)//1000
            for x in range(w)] for y in range(h)]
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if lum[y][x] >= seuil:
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
    cote = max(maxx-minx+1, maxy-miny+1)
    cote += 2*int(cote*marge)
    cx, cy = (minx+maxx)//2, (miny+maxy)//2
    x0, y0 = cx-cote//2, cy-cote//2
    px = []
    for j in range(taille):
        ligne = bytearray()
        for i in range(taille):
            sx0, sx1 = x0 + i*cote//taille, x0 + (i+1)*cote//taille
            sy0, sy1 = y0 + j*cote//taille, y0 + (j+1)*cote//taille
            s = n = 0
            for yy in range(sy0, max(sy0+1, sy1)):
                for xx in range(sx0, max(sx0+1, sx1)):
                    n += 1
                    if 0 <= yy < h and 0 <= xx < w and lum[yy][xx] >= seuil:
                        s += 255
            ligne += bytes((255, 255, 255, s//max(n, 1)))
        px.append(ligne)
    return png_encode(taille, taille, px)


def alpha_ratios(p):
    w, h, ct, nc, rows = png_decode(p)
    if ct not in (4, 6): return w, h, ct, None
    tot = w*h; op = tr = 0
    for r in rows:
        for x in range(w):
            a = r[x*nc + nc-1]
            if a == 255: op += 1
            elif a == 0: tr += 1
    return w, h, ct, (tot, op, tr)


SRC_SW = io.open(SW, encoding="utf-8").read()


def tests():
    # === A. LA CAUSE — documentee et verrouillee ===
    w, h, ct, st = alpha_ratios(os.path.join(PUB, "logo192.png"))
    verifier("A1. l'ancienne icone de badge est ENTIEREMENT opaque (la cause)",
             st and st[1] == st[0], str(st))
    verifier("A2. ... donc sa silhouette Android est un carre plein",
             st and st[2] == 0, "pixels transparents : %s" % (st[2] if st else '?'))

    # === B. LE NOUVEL ASSET ===
    verifier("B1. le badge existe", os.path.exists(BADGE))
    w, h, ct, st = alpha_ratios(BADGE)
    verifier("B2. 96x96", (w, h) == (96, 96), "%sx%s" % (w, h))
    verifier("B3. RGBA (canal alpha present)", ct == 6, "type=%s" % ct)
    verifier("B4. fond TRANSPARENT et non opaque",
             st and st[2] > st[0]*0.5, "transparents=%.1f%%" % (100*st[2]/st[0] if st else 0))
    verifier("B5. un glyphe est bien present (pas une image vide)",
             st and st[1] > st[0]*0.03, "opaques=%.1f%%" % (100*st[1]/st[0] if st else 0))
    verifier("B6. masque PLEIN : l'interieur est totalement opaque, pas delave",
             st and st[1] > 0 and (st[0]-st[1]-st[2]) < st[0]*0.10,
             "semi-transparents=%.1f%%" % (100*(st[0]-st[1]-st[2])/st[0] if st else 0))
    verifier("B7. leger (< 20 ko)", os.path.getsize(BADGE) < 20000,
             "%d octets" % os.path.getsize(BADGE))

    # === C. IL VIENT DE L'ASSET OFFICIEL, PAS D'UN REDESSIN ===
    attendu = deriver_silhouette(SOURCE)
    livre = open(BADGE, "rb").read()
    verifier("C1. le badge livre est EXACTEMENT la silhouette de logo512.png",
             attendu == livre,
             "regenere=%d o, livre=%d o" % (len(attendu), len(livre)))

    # === D. LE SERVICE WORKER ===
    verifier("D1. `badge` pointe le nouvel asset",
             "badge: '/notification-badge-96.png'" in SRC_SW, "")
    verifier("D2. `badge` ne pointe plus le logo couleur",
             "badge: '/logo192.png'" not in SRC_SW, "")
    verifier("D3. `icon` reste le logo COULEUR (grande icone, rendue telle quelle)",
             "icon: '/logo192.png'" in SRC_SW, "")
    verifier("D4. le badge est pre-cache", "'/notification-badge-96.png'" in SRC_SW, "")
    verifier("D5. CACHE_NAME bumpe (sinon les anciens clients gardent l'ancien SW)",
             "afroboost-v445" in SRC_SW and "afroboost-v417" not in SRC_SW, "")

    # === E. LE RESTE DU PAYLOAD DE NOTIFICATION EST INTACT ===
    for cle in ("body: data.body || 'Vous avez une nouvelle notification'",
                "vibrate: [200, 100, 200]", "tag: data.tag || 'afroboost-push'",
                "renotify: true", "requireInteraction: false",
                "{ action: 'open', title: 'Voir' }", "{ action: 'close', title: 'Fermer' }",
                "url: data.url || '/?openChat=true'",
                "session_id: data.session_id || null",
                "title = data.title || 'Afroboost'"):
        verifier("E1. option inchangee : %s" % cle[:44], cle in SRC_SW, cle)

    # === F. L'URL AU CLIC EST INCHANGEE ===
    import subprocess
    ancien = subprocess.check_output(["git", "show", "1fe9276:frontend/public/sw.js"],
                                     cwd=RACINE).decode()
    def bloc(txt, evt):
        d = txt.index("addEventListener('%s'" % evt)
        return txt[d:txt.index("});", d)]
    verifier("F1. le handler `notificationclick` est INCHANGE",
             bloc(ancien, "notificationclick") == bloc(SRC_SW, "notificationclick"), "")

    # V446 — CES SONDES SE JUGENT SUR LE LOT V445, PAS SUR L'ARBRE DE TRAVAIL.
    # Bornees a `git diff 1fe9276` (donc a l'arbre courant), elles tombaient des
    # qu'un lot ULTERIEUR touchait `api/server.py` — ce qui est arrive avec V446.
    # C'est la TROISIEME occurrence de ce defaut dans le depot (S9b de V442, F1
    # de V443). La regle, desormais : borner au COMMIT, jamais a l'arbre.
    LOT_V445 = ("1fe9276", "ff5846d")

    # === G. AUCUN IMPACT PWA / iPhone / web ===
    for f in ("manifest.json", "index.html", "logo192.png", "logo512.png",
              "logo192-maskable.png", "logo512-maskable.png", "favicon.ico"):
        a = subprocess.run(["git", "diff", "--quiet", "%s..%s" % LOT_V445, "--",
                            "frontend/public/" + f], cwd=RACINE)
        verifier("G1. %s inchange" % f, a.returncode == 0, "")

    # === H. LE BACKEND : SEULE LA CLE `badge` A BOUGE ===
    for f in ("api/server.py", "api/routes/reservation_routes.py"):
        d = subprocess.check_output(["git", "diff", "%s..%s" % LOT_V445, "--", f],
                                    cwd=RACINE).decode(errors="replace")
        modifiees = [l for l in d.splitlines()
                     if l.startswith("-") and not l.startswith("---")]
        verifier("H1. %s : une seule ligne retiree" % f, len(modifiees) == 1, str(modifiees))
        verifier("H2. %s : c'etait bien la ligne icon/badge" % f,
                 modifiees and '"badge": "/logo192.png"' in modifiees[0], str(modifiees))
        ajoutees = [l for l in d.splitlines()
                    if l.startswith("+") and not l.startswith("+++")]
        code = [l for l in ajoutees if not l[1:].strip().startswith("#")]
        verifier("H3. %s : une seule ligne de code ajoutee" % f, len(code) == 1, str(code))
        verifier("H4. %s : `icon` reste le logo couleur" % f,
                 code and '"icon": "/logo192.png"' in code[0], str(code))

    # === I. AUCUN ENVOI, AUCUNE LOGIQUE TOUCHEE ===
    d = subprocess.check_output(["git", "diff", "--name-only", "%s..%s" % LOT_V445],
                                cwd=RACINE).decode()
    touches = sorted(f for f in d.split() if f)
    verifier("I1. perimetre du lot V445", touches == [
        "api/routes/reservation_routes.py", "api/server.py",
        "frontend/public/notification-badge-96.png", "frontend/public/sw.js",
        "tests/test_v445_icone_notification.py"], str(touches))
    src_py = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    a_py = subprocess.check_output(["git", "show", "1fe9276:api/server.py"],
                                   cwd=RACINE).decode(errors="replace")
    import ast
    def fn(txt, nom):
        """Le code EXECUTE de la fonction. `ast.unparse` supprime commentaires ET
        docstrings : une sonde qui comparerait le texte brut echouerait sur un
        simple commentaire de fin de ligne, sans que rien n'ait change."""
        for x in ast.walk(ast.parse(txt)):
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == nom:
                corps = list(x.body)
                if (corps and isinstance(corps[0], ast.Expr)
                        and isinstance(getattr(corps[0], "value", None), ast.Constant)
                        and isinstance(corps[0].value.value, str)):
                    corps = corps[1:]
                return "\n".join(ast.unparse(n) for n in corps)
        return None
    avant = fn(a_py, "send_push_notification").replace("/logo192.png", "@BADGE@")
    apres = fn(src_py, "send_push_notification").replace(
        "/notification-badge-96.png", "@BADGE@").replace("/logo192.png", "@BADGE@")
    verifier("I2. la LOGIQUE d'envoi push est inchangee (hors la constante badge)",
             avant == apres, "diff de %d caracteres" % abs(len(avant)-len(apres)))

    # Ce test doit etre hors ligne. On inspecte ses IMPORTS reels par AST : une
    # recherche de texte se trouverait elle-meme dans la liste des mots interdits.
    interdits = ("requests", "pymongo", "httpx", "socket", "urllib")
    mods = set()
    for n in ast.walk(ast.parse(io.open(__file__, encoding="utf-8").read())):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("I3. ce test n'importe rien de reseau ni de base",
             not (mods & set(interdits)), str(sorted(mods & set(interdits))))
    verifier("I3b. il n'importe que la bibliotheque standard",
             mods <= {"io", "os", "re", "struct", "sys", "zlib", "subprocess", "ast"},
             str(sorted(mods)))


def main():
    tests()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Notifications REELLEMENT envoyees par cette suite : 0")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
