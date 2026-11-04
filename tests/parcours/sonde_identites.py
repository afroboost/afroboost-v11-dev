#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonde toutes les routes du serveur LOCAL avec plusieurs identités, et compare les réponses.

BANC LOCAL UNIQUEMENT : adresse écrite ici, refus de tourner hors de `reseau_local.sb`.
Elle peut écrire dans `afroboost_pw_test` : recharger cette base ensuite.

    sandbox-exec -f tests/parcours/reseau_local.sb python3 tests/parcours/sonde_identites.py <sortie.json>
"""
import ctypes
import json
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import requests

BASE = "http://127.0.0.1:8001"
SECRET = "pw-local-secret"
ADMIN = "contact.artboost@gmail.com"
COACH = "sonde.coach@example.com"
# Flux qui ne répondent pas à une sonde. `v307-set-jwt-secret` CHANGE le secret du serveur dès qu'elle
# accepte : la sonder invalide tous les jetons suivants et fausse la mesure (constaté le 04/11).
IGNOREES = re.compile(r"/stream|/events$|/sse|/ws\b|/socket|/v307-set-jwt-secret")


def exiger_isolation():
    s = socket.socket()
    s.settimeout(4)
    try:
        s.connect(("1.1.1.1", 443))
        sys.exit("ARRÊT : ce script doit tourner dans reseau_local.sb")
    except PermissionError:
        pass
    pid = int(subprocess.check_output(["lsof", "-nP", "-iTCP:8001", "-sTCP:LISTEN", "-t"]).split()[0])
    if ctypes.CDLL(None).sandbox_check(pid, None, 0) != 1:
        sys.exit("ARRÊT : le serveur 8001 ne tourne pas dans reseau_local.sb")


def jeton(email, role="coach"):
    return jwt.encode({"email": email, "role": role, "iat": int(time.time()), "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")


ESPACE = jwt.encode({"type": "subscriber_space", "email": "abonne.sonde@example.org", "coach_id": ADMIN, "jti": "s", "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")
IDENTITES = {
    "anonyme": {},
    "entete_admin": {"X-User-Email": ADMIN},
    "entete_coach": {"X-User-Email": COACH},
    "jeton_abonne": {"Authorization": f"Bearer {ESPACE}"},
    "jeton_coach": {"Authorization": f"Bearer {jeton(COACH)}"},
    "jeton_admin": {"Authorization": f"Bearer {jeton(ADMIN, 'super_admin')}"},
}


def valeur(schema, composants, profondeur=0):
    """Un corps minimal valide : sans lui, le 422 masque le contrôle d'identité."""
    if profondeur > 4 or not schema:
        return "x"
    if "$ref" in schema:
        return valeur(composants.get(schema["$ref"].split("/")[-1], {}), composants, profondeur + 1)
    for cle in ("anyOf", "oneOf", "allOf"):
        if schema.get(cle):
            return valeur(schema[cle][0], composants, profondeur + 1)
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {k: valeur(schema["properties"][k], composants, profondeur + 1) for k in schema.get("required", []) if k in schema.get("properties", {})}
    if t == "array":
        return []
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return False
    return "sonde"


def sonder(route, composants):
    meth, chemin, op = route
    url = re.sub(r"\{[^}]+\}", "v646-sonde", chemin)
    corps = None
    if meth != "get":
        corps = {}
        contenu = (op.get("requestBody") or {}).get("content", {})
        if "application/json" in contenu:
            corps = valeur(contenu["application/json"].get("schema") or {}, composants)
    params = {p["name"]: "sonde" for p in op.get("parameters", []) if p.get("in") == "query" and p.get("required")}
    res = {"meth": meth.upper(), "chemin": chemin}
    for nom, entetes in IDENTITES.items():
        try:
            r = requests.request(meth, BASE + url, json=corps, params=params, headers=entetes, timeout=8, allow_redirects=False)
            res[nom] = r.status_code
            res[nom + "_taille"] = len(r.content)
        except requests.RequestException as e:
            res[nom] = type(e).__name__
            res[nom + "_taille"] = 0
    return res


def main():
    exiger_isolation()
    spec = requests.get(BASE + "/openapi.json", timeout=30).json()
    composants = spec.get("components", {}).get("schemas", {})
    routes = []
    for chemin, ops in spec["paths"].items():
        if IGNOREES.search(chemin):
            continue
        for meth, op in ops.items():
            if meth in ("get", "post", "put", "patch", "delete"):
                routes.append((meth, chemin, op))
    # Les lectures d'abord : les écritures de la sonde ne doivent pas fausser leur mesure.
    routes.sort(key=lambda r: r[0] != "get")
    lectures = [r for r in routes if r[0] == "get"]
    ecritures = [r for r in routes if r[0] != "get"]
    print("routes:", len(routes), "lectures:", len(lectures), "ecritures:", len(ecritures), flush=True)
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda r: sonder(r, composants), lectures))
    for i, r in enumerate(ecritures):
        res.append(sonder(r, composants))
        if i % 100 == 0:
            print("ecritures", i, flush=True)
    json.dump(res, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("fini", len(res), flush=True)


if __name__ == "__main__":
    main()
