"""Notifie IndexNow (Bing, Yandex, Naver, Seznam, Yep) des URLs du site.

Lit le sitemap du site en ligne. Par défaut, ne soumet que les URLs dont la date
de dernière modification (lastmod) a moins de RECENT_DAYS jours. Avec INDEXNOW_MODE=all,
soumet tout le sitemap.

Variables d'environnement : SITE_URL (avec slash final), INDEXNOW_KEY, INDEXNOW_MODE (recent|all).
Google ne prend pas en charge IndexNow : il passe toujours par le sitemap et Search Console.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

RECENT_DAYS = 7
ENDPOINT = "https://api.indexnow.org/IndexNow"

site = os.environ["SITE_URL"].rstrip("/") + "/"
key = os.environ["INDEXNOW_KEY"]
mode = os.environ.get("INDEXNOW_MODE", "recent")
host = urlparse(site).netloc
key_location = f"{site}{key}.txt"


def fetch(url, retries=6, wait=10):
    """Lit une URL, avec quelques essais le temps que la mise en ligne se propage."""
    last = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(wait)
    raise RuntimeError(f"Lecture impossible de {url} : {last}")


# Le fichier clé doit être en ligne et contenir exactement la clé, sinon IndexNow rejette l'envoi.
served = fetch(key_location).strip()
if served != key:
    sys.exit(f"Le fichier clé {key_location} ne contient pas la clé attendue.")

sitemap = fetch(f"{site}sitemap.xml")
cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
urls = []
for loc, lastmod in re.findall(
    r"<url><loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?", sitemap
):
    if urlparse(loc).netloc != host:
        continue
    if mode != "all" and lastmod:
        when = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < cutoff:
            continue
    urls.append(loc)

if not urls:
    print("Aucune URL récente à soumettre.")
    sys.exit(0)

body = json.dumps(
    {"host": host, "key": key, "keyLocation": key_location, "urlList": urls}
).encode("utf-8")
req = urllib.request.Request(
    ENDPOINT,
    data=body,
    headers={"Content-Type": "application/json; charset=utf-8"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"IndexNow : HTTP {r.status}, {len(urls)} URL(s) soumise(s) pour {host}.")
except urllib.error.HTTPError as e:
    # 200 et 202 sont des succès. 403 = clé invalide, 422 = URLs hors du host, 429 = trop de requêtes.
    sys.exit(f"IndexNow a répondu HTTP {e.code} : {e.read().decode('utf-8', 'replace')}")
