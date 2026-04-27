#!/usr/bin/env python3
"""
Music-AI-Detection-Standard — Scoring Script v0.1
Calcule automatiquement le score de suspicion d'un artiste
en interrogeant MusicBrainz, Discogs, Wikidata et Spotify.

Usage:
    python mads_score.py --artist "Nom de l'artiste"
    python mads_score.py --artist "Nom de l'artiste" --discogs-token TOKEN
    python mads_score.py --artist "Nom de l'artiste" --discogs-token TOKEN \
                         --spotify-id CLIENT_ID --spotify-secret CLIENT_SECRET

Clés API :
    Discogs  : https://www.discogs.com/settings/developers -> Generate Token
    Spotify  : https://developer.spotify.com -> Create App
    Wikidata : aucune cle requise (SPARQL public)
"""

import argparse
import time
import sys
from datetime import datetime
import requests
import httpx
_client = httpx.Client(verify=True, timeout=15)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
DISCOGS_BASE     = "https://api.discogs.com"
WIKIDATA_SPARQL  = "https://query.wikidata.org/sparql"

HEADERS_MB = {
    "User-Agent": "MADS-Scorer/0.1 (music-ai-detection-standard; contact@example.com)",
    "Accept": "application/json",
}
HEADERS_WD = {
    "User-Agent": "MADS-Scorer/0.1",
    "Accept": "application/sparql-results+json",
}

AI_BOOM_YEAR        = 2022
VELOCITY_HIGH       = 30
VELOCITY_SUSPICIOUS = 15


# ─────────────────────────────────────────────
# HELPERS — RATE LIMITERS
# ─────────────────────────────────────────────

def mb_get(endpoint, params, retries=4):
    params["fmt"] = "json"
    for attempt in range(retries):
        try:
            r = _client.get(
                f"{MUSICBRAINZ_BASE}/{endpoint}",
                params=params,
                headers=HEADERS_MB,
                timeout=30,  # augmenté de 15 à 30
            )
            time.sleep(1.1)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = 10 * (2 ** attempt)  # 10s, 20s, 40s, 80s
            print(f"       MusicBrainz timeout (tentative {attempt+1}/{retries}), "
                  f"retry dans {wait}s... ({e})")
            time.sleep(wait)
    raise ConnectionError(f"MusicBrainz inaccessible après {retries} tentatives.")


def discogs_get(endpoint, params, token):
    """Discogs avec token — max 60 req/min."""
    headers = {
        "User-Agent": "MADS-Scorer/0.1",
        "Authorization": f"Discogs token={token}",
    }
    r = _client.get(f"{DISCOGS_BASE}{endpoint}", params=params,
                     headers=headers, timeout=15)
    time.sleep(1.0)
    r.raise_for_status()
    return r.json()


def discogs_get_anon(endpoint, params):
    """Discogs sans token — max 25 req/min."""
    headers = {"User-Agent": "MADS-Scorer/0.1"}
    r = _client.get(f"{DISCOGS_BASE}{endpoint}", params=params,
                     headers=headers, timeout=15)
    time.sleep(2.5)
    r.raise_for_status()
    return r.json()


def wikidata_query(sparql):
    """Wikidata SPARQL endpoint."""
    r = _client.get(
        WIKIDATA_SPARQL,
        params={"query": sparql, "format": "json"},
        headers=HEADERS_WD,
        timeout=20,
    )
    time.sleep(1.0)
    r.raise_for_status()
    return r.json()


def spotify_token(client_id, client_secret):
    r = _client.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=10,
    )
    return r.json()["access_token"] if r.status_code == 200 else None


def spotify_get(endpoint, token, params=None):
    if params is None:
        params = {}
    headers = {"Authorization": f"Bearer {token}"}
    r = _client.get(f"https://api.spotify.com/v1/{endpoint}",
                     headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────
# DATA COLLECTION — MUSICBRAINZ
# ─────────────────────────────────────────────

def search_artist_mb(name):
    data = mb_get("artist", {"query": name, "limit": 5})
    artists = data.get("artists", [])
    return max(artists, key=lambda a: a.get("score", 0)) if artists else None


def get_releases_mb(artist_id):
    releases, offset, limit = [], 0, 100
    while True:
        data = mb_get("release", {
            "artist": artist_id, "limit": limit, "offset": offset,
            "inc": "artist-credits labels recordings",
        })
        batch = data.get("releases", [])
        releases.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return releases


def get_works_mb(artist_id):
    works, offset, limit = [], 0, 100
    while True:
        data = mb_get("work", {
            "artist": artist_id, "limit": limit,
            "offset": offset, "inc": "artist-rels",
        })
        batch = data.get("works", [])
        works.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return works


def get_songwriter_relations_mb(artist_id):
    """Analyse les vraies relations creatives sur les recordings."""
    recordings, offset, limit = [], 0, 100
    while len(recordings) < 300:
        data = mb_get("recording", {
            "artist": artist_id, "limit": limit, "offset": offset,
            "inc": "artist-rels work-rels",
        })
        batch = data.get("recordings", [])
        recordings.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    roles = {"writer": 0, "composer": 0, "lyricist": 0,
              "producer": 0, "mix": 0, "other": 0}
    creation_roles = {"writer", "composer", "lyricist", "producer",
                      "mix", "recording", "mastering", "programming"}
    solo_all_roles = 0

    for rec in recordings:
        rec_roles, all_credited = set(), set()
        for rel in rec.get("relations", []):
            rel_type = rel.get("type", "").lower()
            cid = rel.get("artist", {}).get("id", "")
            all_credited.add(cid)
            if cid == artist_id:
                if "writer" in rel_type:
                    roles["writer"] += 1; rec_roles.add("writer")
                elif "composer" in rel_type:
                    roles["composer"] += 1; rec_roles.add("composer")
                elif "lyricist" in rel_type:
                    roles["lyricist"] += 1; rec_roles.add("lyricist")
                elif "producer" in rel_type:
                    roles["producer"] += 1; rec_roles.add("producer")
                elif "mix" in rel_type or "engineer" in rel_type:
                    roles["mix"] += 1; rec_roles.add("mix")
                else:
                    roles["other"] += 1
        if len(rec_roles & creation_roles) >= 3 and not (all_credited - {artist_id}):
            solo_all_roles += 1

    return {
        "recordings_analyzed": len(recordings),
        "roles": roles,
        "solo_all_roles_count": solo_all_roles,
        "has_any_creation_credit": any(
            v > 0 for k, v in roles.items() if k in creation_roles
        ),
    }


def get_events_mb(artist_id):
    data = mb_get("event", {"artist": artist_id, "limit": 100})
    return data.get("events", [])


# ─────────────────────────────────────────────
# DATA COLLECTION — DISCOGS
# ─────────────────────────────────────────────

def search_artist_discogs(name, token):
    params = {"q": name, "type": "artist", "per_page": 5}
    try:
        data = discogs_get("/database/search", params, token) if token \
               else discogs_get_anon("/database/search", params)
        results = data.get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def get_artist_releases_discogs(artist_id, token):
    releases, page = [], 1
    while len(releases) < 200:
        try:
            per_page = 100 if token else 50
            data = discogs_get(f"/artists/{artist_id}/releases",
                               {"sort": "year", "per_page": per_page, "page": page}, token) \
                   if token else \
                   discogs_get_anon(f"/artists/{artist_id}/releases",
                                    {"sort": "year", "per_page": per_page, "page": page})
            batch = data.get("releases", [])
            releases.extend(batch)
            if not data.get("pagination", {}).get("urls", {}).get("next"):
                break
            page += 1
        except Exception:
            break
    return releases


def analyze_discogs(name, token):
    """
    Collecte Discogs :
    - Presence physique (vinyl, CD, cassette)
    - Annee de premiere release
    - Signal d'authenticite via marketplace physique
    """
    result = {
        "found": False, "artist_id": None,
        "total_releases": 0, "physical_releases": 0,
        "earliest_year": None, "has_pre2020": False,
        "has_vinyl": False, "has_cd": False,
    }

    artist = search_artist_discogs(name, token)
    if not artist:
        return result

    result["found"] = True
    result["artist_id"] = artist.get("id")

    releases = get_artist_releases_discogs(artist["id"], token)
    result["total_releases"] = len(releases)

    years, physical_count = [], 0
    for rel in releases:
        year = rel.get("year")
        if year and isinstance(year, int) and year > 1900:
            years.append(year)
        fmt  = str(rel.get("format", "")).lower()
        role = str(rel.get("role",   "")).lower()
        if role in ("main", ""):
            if any(f in fmt for f in ("vinyl", "lp", '7"', '10"', '12"')):
                result["has_vinyl"] = True
                physical_count += 1
            elif "cd" in fmt or "cassette" in fmt:
                result["has_cd"] = True
                physical_count += 1

    result["physical_releases"] = physical_count
    if years:
        result["earliest_year"] = min(years)
        result["has_pre2020"]   = min(years) < 2020

    return result


# ─────────────────────────────────────────────
# DATA COLLECTION — WIKIDATA
# ─────────────────────────────────────────────

def search_wikidata(name):
    """
    Interroge Wikidata via SPARQL.
    Recupere : naissance, nationalite, genres, labels,
    instruments, awards, presence Wikipedia.
    """
    result = {
        "found": False, "qid": None,
        "birth_year": None, "nationalities": [],
        "genres": [], "labels": [], "instruments": [],
        "awards": [], "wikipedia_langs": [],
        "has_wikipedia": False, "is_human": False, "is_group": False,
    }

    # Etape 1 : recherche via l'API de recherche Wikidata (plus robuste que SPARQL direct)
    try:
        r = _client.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbsearchentities", "search": name,
                    "language": "en", "type": "item", "format": "json", "limit": 5},
            headers=HEADERS_WD, timeout=10,
        )
        time.sleep(1.0)
        search_results = r.json().get("search", [])
    except Exception:
        return result

    if not search_results:
        return result

    qid = search_results[0]["id"]
    result["found"] = True
    result["qid"]   = qid

    # Etape 2 : recupere les details via SPARQL sur le QID trouve
    sparql = f"""
    SELECT ?dob ?type ?nationalityLabel ?genreLabel
           ?labelNameLabel ?instrumentLabel ?awardLabel ?sitelink
    WHERE {{
      OPTIONAL {{ wd:{qid} wdt:P569  ?dob . }}
      OPTIONAL {{ wd:{qid} wdt:P31   ?type . }}
      OPTIONAL {{ wd:{qid} wdt:P27   ?nationality . }}
      OPTIONAL {{ wd:{qid} wdt:P136  ?genre . }}
      OPTIONAL {{ wd:{qid} wdt:P264  ?labelName . }}
      OPTIONAL {{ wd:{qid} wdt:P1303 ?instrument . }}
      OPTIONAL {{ wd:{qid} wdt:P166  ?award . }}
      OPTIONAL {{
        ?sitelink schema:about wd:{qid} ;
                  schema:isPartOf [ wikibase:wikiGroup "wikipedia" ] .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr". }}
    }}
    LIMIT 30
    """

    try:
        data = wikidata_query(sparql)
        bindings = data.get("results", {}).get("bindings", [])
    except Exception:
        return result  # On a quand meme le QID, c'est utile

    for b in bindings:
        if "dob" in b and not result["birth_year"]:
            try:
                result["birth_year"] = int(b["dob"]["value"][:4])
            except Exception:
                pass

        if "type" in b:
            t = b["type"]["value"]
            if "Q5"      in t: result["is_human"] = True
            if "Q215380" in t: result["is_group"] = True

        for field, key in [
            ("nationalityLabel", "nationalities"),
            ("genreLabel",       "genres"),
            ("labelNameLabel",   "labels"),
            ("instrumentLabel",  "instruments"),
            ("awardLabel",       "awards"),
        ]:
            if field in b:
                val = b[field]["value"]
                if val and not val.startswith("Q") and val not in result[key]:
                    result[key].append(val)

        if "sitelink" in b:
            sl = b["sitelink"]["value"]
            if sl not in result["wikipedia_langs"]:
                result["wikipedia_langs"].append(sl)

    result["has_wikipedia"] = len(result["wikipedia_langs"]) > 0
    return result


# ─────────────────────────────────────────────
# DATA COLLECTION — SPOTIFY
# ─────────────────────────────────────────────

def search_artist_spotify(name, token):
    data = spotify_get("search", token, {"q": name, "type": "artist", "limit": 1})
    items = data.get("artists", {}).get("items", [])
    return items[0] if items else None


def get_albums_spotify(artist_id, token):
    albums = []
    params = {"include_groups": "album,single", "limit": 50, "market": "FR"}
    while True:
        data = spotify_get(f"artists/{artist_id}/albums", token, params)
        albums.extend(data.get("items", []))
        if not data.get("next"):
            break
        params["offset"] = params.get("offset", 0) + 50
    return albums


# ─────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────

def analyze(artist_name, discogs_token=None, spotify_creds=None):
    results = {
        "artist_name": artist_name,
        "sources": {}, "criteria": {},
        "score": 0, "verdict": "", "warnings": [],
    }

    print(f"\n  Analyse de '{artist_name}'...")

    # ── 1. MusicBrainz ───────────────────────
    print("\n  [1/4] MusicBrainz")
    artist_mb = search_artist_mb(artist_name)
    mb_id = None
    if not artist_mb:
        results["warnings"].append("Artiste introuvable sur MusicBrainz.")
        print("       Introuvable")
    else:
        mb_id = artist_mb["id"]
        results["sources"]["musicbrainz_id"]         = mb_id
        results["sources"]["musicbrainz_confidence"] = artist_mb.get("score")
        print(f"       OK : {artist_mb.get('name')} (confiance : {artist_mb.get('score')}%)")

    releases_mb, works_mb, songwriter_data, events_mb = [], [], {}, []
    if mb_id:
        releases_mb     = get_releases_mb(mb_id)
        print(f"       -> {len(releases_mb)} releases")
        works_mb        = get_works_mb(mb_id)
        print(f"       -> {len(works_mb)} oeuvres creditees")
        songwriter_data = get_songwriter_relations_mb(mb_id)
        ro = songwriter_data.get("roles", {})
        print(f"       -> Roles : writer={ro.get('writer',0)}, "
              f"composer={ro.get('composer',0)}, producer={ro.get('producer',0)}")
        events_mb = get_events_mb(mb_id)
        print(f"       -> {len(events_mb)} evenements live")

    # ── 2. Discogs ───────────────────────────
    print("\n  [2/4] Discogs")
    discogs_data = analyze_discogs(artist_name, discogs_token)
    if discogs_data["found"]:
        results["sources"]["discogs_id"] = discogs_data["artist_id"]
        print(f"       OK (ID {discogs_data['artist_id']})")
        print(f"       -> {discogs_data['total_releases']} releases | "
              f"{discogs_data['physical_releases']} physiques | "
              f"Vinyl: {'Oui' if discogs_data['has_vinyl'] else 'Non'} | "
              f"Premiere: {discogs_data['earliest_year'] or 'N/A'}")
    else:
        print("       Introuvable")
        results["warnings"].append("Artiste introuvable sur Discogs.")

    # ── 3. Wikidata ──────────────────────────
    print("\n  [3/4] Wikidata")
    wikidata = search_wikidata(artist_name)
    if wikidata["found"]:
        results["sources"]["wikidata_qid"] = wikidata["qid"]
        print(f"       OK : QID {wikidata['qid']} | "
              f"{'Humain' if wikidata['is_human'] else 'Groupe' if wikidata['is_group'] else 'Entite'}")
        print(f"       -> Naissance: {wikidata['birth_year'] or 'N/A'} | "
              f"Wikipedia: {len(wikidata['wikipedia_langs'])} langue(s)")
        if wikidata["genres"]:
            print(f"       -> Genres : {', '.join(wikidata['genres'][:3])}")
        if wikidata["labels"]:
            print(f"       -> Labels : {', '.join(wikidata['labels'][:3])}")
    else:
        print("       Introuvable")
        results["warnings"].append("Artiste introuvable sur Wikidata.")

    # ── 4. Spotify ───────────────────────────
    albums_spotify = []
    print("\n  [4/4] Spotify")
    if spotify_creds:
        tok = spotify_token(*spotify_creds)
        if tok:
            artist_sp = search_artist_spotify(artist_name, tok)
            if artist_sp:
                followers = artist_sp.get("followers", {}).get("total", 0)
                results["sources"]["spotify_id"]        = artist_sp["id"]
                results["sources"]["spotify_followers"] = followers
                print(f"       OK : {artist_sp['name']} ({followers:,} followers)")
                albums_spotify = get_albums_spotify(artist_sp["id"], tok)
                print(f"       -> {len(albums_spotify)} albums/singles")
            else:
                results["warnings"].append("Artiste introuvable sur Spotify.")
                print("       Introuvable")
        else:
            results["warnings"].append("Token Spotify invalide.")
            print("       Token invalide")
    else:
        print("       Non configure (optionnel)")

    # ─────────────────────────────────────────
    # CALCUL DES CRITERES
    # ─────────────────────────────────────────
    print("\n  Calcul du score...")

    # Agregation des annees de release (MB + Spotify)
    years = []
    for rel in releases_mb:
        d = rel.get("date", "")
        if d and len(d) >= 4:
            try: years.append(int(d[:4]))
            except ValueError: pass
    for a in albums_spotify:
        d = a.get("release_date", "")
        if d and len(d) >= 4:
            try: years.append(int(d[:4]))
            except ValueError: pass

    year_counts = {}
    for y in years:
        year_counts[y] = year_counts.get(y, 0) + 1

    pre_boom  = {y: c for y, c in year_counts.items() if y <= AI_BOOM_YEAR}
    post_boom = {y: c for y, c in year_counts.items() if y > AI_BOOM_YEAR}
    max_pre   = max(pre_boom.values(),  default=0)
    max_post  = max(post_boom.values(), default=0)
    total_tracks = len(years)
    avg_post  = sum(post_boom.values()) / len(post_boom) if post_boom else 0

    results["sources"]["total_releases_found"]   = total_tracks
    results["sources"]["max_releases_pre_boom"]  = max_pre
    results["sources"]["max_releases_post_boom"] = max_post
    results["sources"]["year_distribution"]      = dict(sorted(year_counts.items()))

    # Critere 1 : Velocity Burst
    v_spike      = max_post > 0 and max_pre > 0 and max_post >= max_pre * 5
    v_spike_cold = max_post > 50 and max_pre == 0
    results["criteria"]["release_velocity_burst"] = {
        "triggered": v_spike or v_spike_cold,
        "points":    3 if (v_spike or v_spike_cold) else 0,
        "detail":    f"Pre-boom max: {max_pre}/an -> Post-boom max: {max_post}/an",
    }

    # Critere 2 : Raw Velocity
    if avg_post > VELOCITY_HIGH:
        vp, vs = 3, "High Alert"
    elif avg_post > VELOCITY_SUSPICIOUS:
        vp, vs = 1, "Suspicious"
    else:
        vp, vs = 0, "Normal"
    results["criteria"]["raw_velocity"] = {
        "triggered": vp > 0,
        "points":    vp,
        "detail":    f"Moy. post-{AI_BOOM_YEAR}: {avg_post:.1f} tracks/an ({vs})",
    }

    # Critere 3 : Missing Songwriter Credits
    has_works    = len(works_mb) > 0
    has_creation = songwriter_data.get("has_any_creation_credit", False)
    sd_roles     = songwriter_data.get("roles", {})
    rec_analyzed = songwriter_data.get("recordings_analyzed", 0)
    missing      = not has_works and not has_creation and total_tracks > 20
    roles_str    = (f"writer={sd_roles.get('writer',0)}, "
                    f"composer={sd_roles.get('composer',0)}, "
                    f"producer={sd_roles.get('producer',0)}")
    results["criteria"]["missing_songwriter_credits"] = {
        "triggered": missing,
        "points":    3 if missing else 0,
        "detail": (
            f"Aucun credit sur {total_tracks} releases ({rec_analyzed} recordings)"
            if missing else
            f"{len(works_mb)} Works MB | {rec_analyzed} recordings | {roles_str}"
        ),
    }

    # Critere 4 : Presence reelle (MB + Discogs + Wikidata)
    has_mb_events    = len(events_mb) > 0
    has_phys         = discogs_data["physical_releases"] > 0
    has_wiki_id      = wikidata["found"] and (wikidata["is_human"] or wikidata["is_group"])
    has_presence     = has_mb_events or has_phys or has_wiki_id
    presence_parts   = []
    if has_mb_events: presence_parts.append(f"{len(events_mb)} concerts (MB)")
    if has_phys:      presence_parts.append(f"{discogs_data['physical_releases']} releases physiques (Discogs)")
    if has_wiki_id:   presence_parts.append("Identite verifiee (Wikidata)")
    if not presence_parts: presence_parts.append("Aucune presence detectee")
    results["criteria"]["lack_of_real_world_presence"] = {
        "triggered": not has_presence,
        "points":    3 if not has_presence else 0,
        "detail":    " | ".join(presence_parts),
    }

    # Critere 5 : Copied Metadata
    credit_sets = []
    for rel in releases_mb:
        c = tuple(sorted(ac.get("artist", {}).get("id", "")
                         for ac in rel.get("artist-credit", [])))
        credit_sets.append(c)
    unique_credits = len(set(credit_sets))
    copied = total_tracks > 50 and unique_credits == 1
    results["criteria"]["copied_metadata"] = {
        "triggered": copied,
        "points":    3 if copied else 0,
        "detail":    f"{unique_credits} combinaison(s) de credits sur {total_tracks} releases",
    }

    # Critere 6 : Database Absence (absent des 3 bases)
    absent_all = (mb_id is None and not discogs_data["found"]
                  and not wikidata["found"] and total_tracks == 0)
    absent_parts = []
    if mb_id is None:            absent_parts.append("Absent MB")
    if not discogs_data["found"]:absent_parts.append("Absent Discogs")
    if not wikidata["found"]:    absent_parts.append("Absent Wikidata")
    results["criteria"]["database_absence"] = {
        "triggered": absent_all,
        "points":    1 if absent_all else 0,
        "detail": (
            " | ".join(absent_parts) if absent_parts
            else "Present sur au moins une base"
        ),
    }

    # Critere 7 : Solo Credits Mass Catalog
    solo_count = songwriter_data.get("solo_all_roles_count", 0)
    rec_count  = max(songwriter_data.get("recordings_analyzed", 1), 1)
    solo_ratio = solo_count / rec_count
    solo_mass  = total_tracks > 30 and solo_ratio > 0.4
    results["criteria"]["solo_credits_mass_catalog"] = {
        "triggered": solo_mass,
        "points":    1 if solo_mass else 0,
        "detail":    (f"{solo_count}/{rec_count} recordings ({solo_ratio:.0%}) "
                      f"avec artiste seul sur tous les roles creatifs"),
    }

    # ── FACTEURS PROTECTEURS ─────────────────

    # Pre-2020 : MB + Discogs + Wikidata naissance
    has_pre2020_mb  = any(y < 2020 for y in years)
    has_pre2020_dc  = discogs_data.get("has_pre2020", False)
    birth_year      = wikidata.get("birth_year")
    has_pre2020_wd  = birth_year is not None and birth_year < 2020
    has_pre2020     = has_pre2020_mb or has_pre2020_dc or has_pre2020_wd
    pre2020_parts   = []
    if has_pre2020_mb: pre2020_parts.append(f"MB release {min(years, default='?')}")
    if has_pre2020_dc: pre2020_parts.append(f"Discogs {discogs_data['earliest_year']}")
    if has_pre2020_wd: pre2020_parts.append(f"Naissance {birth_year} (Wikidata)")
    results["criteria"]["pre_2020_history"] = {
        "triggered": has_pre2020,
        "points":    -3 if has_pre2020 else 0,
        "detail": (
            " | ".join(pre2020_parts) if pre2020_parts
            else "Aucun historique pre-2020 detecte"
        ),
    }

    # Live footprint : MB events + Discogs physique + Wikipedia
    has_wiki_wp  = wikidata.get("has_wikipedia", False)
    has_live     = has_mb_events or has_phys or has_wiki_wp
    live_parts   = []
    if has_mb_events: live_parts.append(f"{len(events_mb)} concerts (MB)")
    if has_phys:      live_parts.append("Presence physique (Discogs)")
    if has_wiki_wp:   live_parts.append(f"Wikipedia ({len(wikidata['wikipedia_langs'])} langue(s))")
    results["criteria"]["verified_live_footprint"] = {
        "triggered": has_live,
        "points":    -3 if has_live else 0,
        "detail": (
            " | ".join(live_parts) if live_parts
            else "Aucune presence verifiable"
        ),
    }

    # Score final
    total_score = sum(c["points"] for c in results["criteria"].values())
    results["score"]   = total_score
    results["verdict"] = (
        "AI Probable"  if total_score >= 7 else
        "Unverified"   if total_score >= 3 else
        "Human Artist"
    )
    results["sources"]["discogs"]  = discogs_data
    results["sources"]["wikidata"] = wikidata
    return results


# ─────────────────────────────────────────────
# COULEURS ANSI
# ─────────────────────────────────────────────

class C:
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

def col(text, *codes):
    return "".join(codes) + str(text) + C.RESET


# ─────────────────────────────────────────────
# AFFICHAGE
# ─────────────────────────────────────────────

VERDICT_ICON = {
    "AI Probable":  col("● AI Probable",  C.BOLD, C.RED),
    "Unverified":   col("● Unverified",   C.BOLD, C.YELLOW),
    "Human Artist": col("● Human Artist", C.BOLD, C.GREEN),
}

def print_report(r):
    wd = r["sources"].get("wikidata", {})
    dc = r["sources"].get("discogs",  {})

    print("\n" + col("═" * 60, C.CYAN))
    print(col(f"  MADS REPORT v0.1 — {r['artist_name'].upper()}", C.BOLD, C.CYAN))
    print(col("═" * 60, C.CYAN))

    if wd.get("found"):
        kind = "Humain" if wd["is_human"] else ("Groupe" if wd["is_group"] else "Entite")
        print(f"\n  {col('Wikidata', C.BLUE)} QID : {wd.get('qid')} ({kind})")
        if wd.get("genres"):
            print(f"  {col('Genres      :', C.DIM)} {', '.join(wd['genres'][:5])}")
        if wd.get("labels"):
            print(f"  {col('Labels      :', C.DIM)} {', '.join(wd['labels'][:4])}")
        if wd.get("instruments"):
            print(f"  {col('Instruments :', C.DIM)} {', '.join(wd['instruments'][:4])}")
        if wd.get("awards"):
            print(f"  {col('Awards      :', C.DIM)} {', '.join(wd['awards'][:3])}")
        if wd.get("wikipedia_langs"):
            print(f"  {col('Wikipedia   :', C.DIM)} {len(wd['wikipedia_langs'])} langue(s)")

    if dc.get("found"):
        vinyl = col("Oui", C.GREEN) if dc["has_vinyl"] else col("Non", C.DIM)
        cd    = col("Oui", C.GREEN) if dc["has_cd"]    else col("Non", C.DIM)
        print(f"\n  {col('Discogs', C.BLUE)} : {dc['total_releases']} releases | "
              f"{dc['physical_releases']} physiques | "
              f"Vinyl: {vinyl} | CD: {cd} | "
              f"Premiere: {dc['earliest_year'] or 'N/A'}")

    print("\n" + col("─" * 60, C.DIM))
    print(col("  CRITERES\n", C.BOLD))

    labels = {
        "release_velocity_burst":      "Velocity Burst (spike post-2022)",
        "raw_velocity":                "Raw Velocity (tracks/an)",
        "missing_songwriter_credits":  "Missing Songwriter Credits",
        "lack_of_real_world_presence": "Lack of Real-World Presence",
        "copied_metadata":             "Copied Metadata",
        "database_absence":            "Database Absence",
        "solo_credits_mass_catalog":   "Solo Credits / Mass Catalog",
        "pre_2020_history":            "Pre-2020 History (protecteur)",
        "verified_live_footprint":     "Verified Live Footprint (protecteur)",
    }

    for key, label in labels.items():
        c         = r["criteria"].get(key, {})
        pts       = c.get("points", 0)
        detail    = c.get("detail", "")
        triggered = c.get("triggered", False)

        if pts > 1:
            icon      = col("●", C.RED)
            pts_str   = col(f"{pts:+d} pts", C.RED)
            lbl_str   = col(label, C.RED)
            arrow     = col(" ◄", C.RED) if triggered else ""
        elif pts == 1:
            icon      = col("●", C.YELLOW)
            pts_str   = col(f"{pts:+d} pts", C.YELLOW)
            lbl_str   = col(label, C.YELLOW)
            arrow     = col(" ◄", C.YELLOW) if triggered else ""
        elif pts < 0:
            icon      = col("●", C.GREEN)
            pts_str   = col(f"{pts:+d} pts", C.GREEN)
            lbl_str   = col(label, C.GREEN)
            arrow     = ""
        else:
            icon      = col("●", C.DIM)
            pts_str   = col(" 0 pts", C.DIM)
            lbl_str   = label
            arrow     = ""

        print(f"  {icon} {lbl_str}")
        print(f"     {pts_str} {col('|', C.DIM)} {col(detail, C.DIM)}{arrow}")

    score     = r["score"]
    score_col = C.RED if score >= 7 else (C.YELLOW if score >= 3 else C.GREEN)
    print(f"\n{col('─' * 60, C.DIM)}")
    print(f"  {col('SCORE TOTAL', C.BOLD)} : {col(f'{score:+d} points', C.BOLD, score_col)}")
    print(f"  {col('VERDICT', C.BOLD)}     : {VERDICT_ICON.get(r['verdict'], r['verdict'])}")
    print(f"{col('─' * 60, C.DIM)}")

    if r["verdict"] == "AI Probable":
        print(f"\n  {col('⚠  Score >= 7 pts.', C.BOLD, C.RED)}")
        print(f"  {col('   Revue humaine obligatoire avant tout label public.', C.RED)}")

    if r["warnings"]:
        print(f"\n  {col('AVERTISSEMENTS :', C.YELLOW)}")
        for w in r["warnings"]:
            print(f"  {col('-', C.YELLOW)} {col(w, C.DIM)}")

    dist = r["sources"].get("year_distribution", {})
    if dist:
        print(f"\n  {col('DISTRIBUTION DES RELEASES PAR ANNEE :', C.BOLD)}")
        max_val = max(dist.values(), default=1)
        for year, count in sorted(dist.items()):
            bar_len = int(count / max_val * 30)
            is_boom = year == AI_BOOM_YEAR
            is_post = year > AI_BOOM_YEAR
            bar_col = C.RED if is_post else (C.YELLOW if is_boom else C.CYAN)
            bar     = col("█" * bar_len, bar_col)
            marker  = col("  ← AI boom", C.YELLOW) if is_boom else ""
            print(f"  {col(year, C.DIM)} | {bar:<30} {col(count, C.DIM)}{marker}")
    print()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MADS Scorer v0.1 — Score de suspicion IA d'un artiste musical"
    )
    parser.add_argument("--artist",         required=True,
                        help="Nom de l'artiste a analyser")
    parser.add_argument("--discogs-token",
                        help="Token Discogs (optionnel, ameliore le rate limit)")
    parser.add_argument("--spotify-id",
                        help="Spotify Client ID (optionnel)")
    parser.add_argument("--spotify-secret",
                        help="Spotify Client Secret (optionnel)")
    args = parser.parse_args()

    spotify_creds = None
    if args.spotify_id and args.spotify_secret:
        spotify_creds = (args.spotify_id, args.spotify_secret)
    elif args.spotify_id or args.spotify_secret:
        print("Spotify : fournissez --spotify-id ET --spotify-secret ensemble.")

    try:
        results = analyze(args.artist, args.discogs_token, spotify_creds)
        print_report(results)
    except requests.exceptions.HTTPError as e:
        print(f"\nErreur HTTP : {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
