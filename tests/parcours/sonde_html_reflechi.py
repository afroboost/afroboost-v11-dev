#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cherche, sur le serveur LOCAL, les routes GET qui renvoient une entrée non échappée dans du HTML.

Un texte d'adresse recopié tel quel dans une page HTML s'exécute sur le domaine du site, là où
le navigateur garde le jeton de session. Le marqueur ne fait rien : il est seulement recherché.

    sandbox-exec -f tests/parcours/reseau_local.sb python3 tests/parcours/sonde_html_reflechi.py
"""
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://127.0.0.1:8001"
MARQUEUR = '"><zz-marqueur-v646>'
# Noms courants qu'une route lit dans l'adresse sans les déclarer à FastAPI.
PARAMS = ("error", "error_description", "message", "code", "state", "token", "email", "name", "q", "ref", "url", "next", "session_id", "status")


def sonder(chemin):
    url = re.sub(r"\{[^}]+\}", requests.utils.quote(MARQUEUR, safe=""), chemin)
    try:
        r = requests.get(BASE + url, params={p: MARQUEUR for p in PARAMS}, timeout=15, allow_redirects=False)
    except requests.RequestException as e:
        return (chemin, "erreur", type(e).__name__)
    html = "html" in r.headers.get("content-type", "")
    if html and "<zz-marqueur-v646>" in r.text:
        return (chemin, "REFLECHI", r.status_code)
    # Une redirection vers une adresse choisie par l'appelant serait un autre défaut, à signaler.
    loc = r.headers.get("location", "")
    if loc.startswith(("zz", '"')) or "zz-marqueur" in loc.split("?")[0]:
        return (chemin, "REDIRECTION", loc[:80])
    return None


def main():
    s = socket.socket()
    s.settimeout(4)
    try:
        s.connect(("1.1.1.1", 443))
        sys.exit("ARRÊT : ce script doit tourner dans reseau_local.sb")
    except PermissionError:
        pass
    spec = requests.get(BASE + "/openapi.json", timeout=30).json()
    chemins = [c for c, ops in spec["paths"].items() if "get" in ops and not re.search(r"/stream|/events$|/sse", c)]
    with ThreadPoolExecutor(6) as ex:
        res = [r for r in ex.map(sonder, chemins) if r]
    print(f"{len(chemins)} routes GET sondées")
    for r in sorted(res, key=str):
        print(" ", *r)
    reflechis = [r for r in res if r[1] == "REFLECHI"]
    print("réfléchies sans échappement :", len(reflechis))
    sys.exit(1 if reflechis else 0)


if __name__ == "__main__":
    main()
