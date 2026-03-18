from flask import Flask, request, jsonify
import requests
import os
from urllib.parse import quote
from difflib import SequenceMatcher

app = Flask(__name__)

OPENALEX_BASE = "https://api.openalex.org"
CROSSREF_BASE = "https://api.crossref.org"

CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "your_email@example.com")

def clean_doi(doi):
    doi = (doi or "").strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "")
    return doi

def similarity(a, b):
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()

def crossref_lookup(doi):
    doi = clean_doi(doi)
    url = f"{CROSSREF_BASE}/works/{quote(doi, safe='')}"

    headers = {
        "User-Agent": f"BibliographyGPT/1.0 (mailto:{CROSSREF_MAILTO})",
        "Accept": "application/json"
    }

    try:
        r = requests.get(url, headers=headers, timeout=20)

        if r.status_code == 404:
            return {"_error": "not_found", "_status_code": 404}

        if r.status_code != 200:
            return {
                "_error": "http_error",
                "_status_code": r.status_code,
                "_text": r.text[:500]
            }

        data = r.json()

        if "message" not in data:
            return {
                "_error": "missing_message",
                "_status_code": 200,
                "_data": data
            }

        return data["message"]

    except requests.exceptions.RequestException as e:
        return {
            "_error": "request_exception",
            "_detail": str(e)
        }
    except ValueError as e:
        return {
            "_error": "json_parse_error",
            "_detail": str(e)
        }

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.get("/search_openalex")
def search_openalex():
    topic = request.args.get("topic")
    if not topic:
        return jsonify({"error": "Missing topic"}), 400

    params = {
        "search": topic,
        "filter": "publication_year:2021-2026,type:article",
        "per_page": 10
    }

    r = requests.get(f"{OPENALEX_BASE}/works", params=params)
    data = r.json()

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("display_name"),
            "doi": item.get("doi"),
            "year": item.get("publication_year")
        })

    return jsonify(results)

@app.get("/verify_doi")
def verify_doi():
    doi = request.args.get("doi")
    if not doi:
        return jsonify({"error": "Missing DOI"}), 400

    msg = crossref_lookup(doi)

    if not msg:
        return jsonify({
            "valid": False,
            "reason": "Unknown lookup failure"
        })

    if isinstance(msg, dict) and msg.get("_error"):
        return jsonify({
            "valid": False,
            "reason": msg["_error"],
            "details": msg
        })

    return jsonify({
        "valid": True,
        "doi": msg.get("DOI"),
        "title": msg.get("title", [None])[0] if msg.get("title") else None,
        "journal": msg.get("container-title", [None])[0] if msg.get("container-title") else None,
        "publisher": msg.get("publisher"),
        "type": msg.get("type")
    })

@app.post("/validate_citation")
def validate_citation():
    data = request.get_json()
    doi = data.get("doi")

    msg = crossref_lookup(doi)
    if not msg:
        return jsonify({"valid_doi": False})

    title_true = msg.get("title", [""])[0]
    title_given = data.get("title", "")

    score = similarity(title_given, title_true)

    return jsonify({
        "valid_doi": True,
        "title_match_score": score,
        "correct_title": title_true
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
