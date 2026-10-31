"""Bibliothèque."""
import re

import requests

from collection_generic import run
from common import UA, secret

ETATS = ["", "Neuf", "Très bon état", "Bon état", "État moyen", "Abîmé"]
FORMATS = ["", "Broché", "Relié", "Poche", "Beau livre", "Bande dessinée", "Revue / magazine", "Partition", "Autre"]
LU = ["", "Oui", "Non", "En cours"]
LANGS = {"fr": "Français", "en": "Anglais", "es": "Espagnol", "it": "Italien", "de": "Allemand", "pt": "Portugais",
         "fre": "Français", "eng": "Anglais", "spa": "Espagnol", "ita": "Italien", "ger": "Allemand"}


def books_lookup(isbn):
    """Recherche un livre par ISBN : Google Books puis Open Library (gratuits, sans clé)."""
    isbn = re.sub(r"[^\dXx]", "", isbn).upper()
    out = {}
    try:
        params = {"q": f"isbn:{isbn}"}
        if secret("google", "books_api_key"):  # facultatif : évite les refus de Google depuis les serveurs Streamlit
            params["key"] = secret("google", "books_api_key")
        r = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, headers=UA, timeout=20)
        items = r.json().get("items", []) if r.ok else []
        if items:
            v = items[0].get("volumeInfo", {})
            out = {
                "titre": v.get("title", "") + (f" — {v['subtitle']}" if v.get("subtitle") else ""),
                "auteur": ", ".join(v.get("authors", [])),
                "editeur": v.get("publisher", ""),
                "annee": str(v.get("publishedDate", ""))[:4],
                "pages": str(v.get("pageCount") or ""),
                "genre": ", ".join(v.get("categories", [])[:2]),
                "langue": LANGS.get(v.get("language", ""), v.get("language", "")),
                "resume": re.sub(r"<[^>]+>", "", v.get("description", "")),
                "_cover": (v.get("imageLinks", {}).get("thumbnail", "") or "").replace("http://", "https://")
                          .replace("&edge=curl", "").replace("zoom=1", "zoom=2"),
            }
    except Exception:
        pass
    try:
        r = requests.get("https://openlibrary.org/api/books", headers=UA, timeout=20,
                         params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"})
        d = (r.json() if r.ok else {}).get(f"ISBN:{isbn}", {})
        if d:
            ol = {
                "titre": d.get("title", "") + (f" — {d['subtitle']}" if d.get("subtitle") else ""),
                "auteur": ", ".join(a.get("name", "") for a in d.get("authors", [])),
                "editeur": ", ".join(p.get("name", "") for p in d.get("publishers", [])),
                "annee": (re.search(r"\d{4}", d.get("publish_date", "")) or [""])[0] if d.get("publish_date") else "",
                "pages": str(d.get("number_of_pages") or ""),
                "genre": ", ".join(s.get("name", "") for s in d.get("subjects", [])[:2]),
                "_cover": (d.get("cover") or {}).get("large") or (d.get("cover") or {}).get("medium", ""),
            }
            if d.get("series"):
                ol["collection"] = ", ".join(map(str, d["series"]))
            for k, v in ol.items():
                if v and not out.get(k):
                    out[k] = v
    except Exception:
        pass
    if out and not out.get("resume"):  # description de l'œuvre sur Open Library, si elle existe
        try:
            ed = requests.get(f"https://openlibrary.org/isbn/{isbn}.json", headers=UA, timeout=20).json()
            work = (ed.get("works") or [{}])[0].get("key")
            if work:
                w = requests.get(f"https://openlibrary.org{work}.json", headers=UA, timeout=20).json()
                desc = w.get("description")
                out["resume"] = (desc.get("value") if isinstance(desc, dict) else desc or "").strip()
        except Exception:
            pass
    if out:
        out["isbn"] = isbn
    return out


run({
    "table": "livres", "prefix": "lv", "icon": "📚",
    "title": "📚 Ma bibliothèque", "caption": "Photo de la couverture ou ISBN → fiche complète grâce à l'IA, Google Books et Open Library.",
    "item": "livre", "item_pl": "livres", "un": "un livre", "le": "le livre", "du": "du livre", "ce": "ce livre",
    "fields": [
        ("titre", "Titre", "text"), ("auteur", "Auteur(s)", "text"), ("editeur", "Éditeur", "text"),
        ("collection", "Collection", "text"), ("annee", "Année", "text"), ("isbn", "ISBN", "text"),
        ("genre", "Genre", "text"), ("langue", "Langue", "text"), ("format", "Format", "select", FORMATS),
        ("pages", "Pages", "text"), ("edition", "Édition (originale, n°, tirage…)", "text"),
        ("etat", "État", "select", ETATS), ("emplacement", "Emplacement (pièce, étagère…)", "text"),
        ("lu", "Lu ?", "select", LU), ("pret", "Prêté à", "text"),
        ("estimation_basse_eur", "Estimation basse (€)", "text"), ("estimation_haute_eur", "Estimation haute (€)", "text"),
        ("resume", "Résumé", "long"), ("notes", "Notes", "long"), ("identification_ia", "Identification IA", "long"),
    ],
    "main": "titre", "sub": "auteur", "text_art": "le résumé", "text_art_de": "du résumé", "text_field": "resume",
    "photos": [("photo_couverture", "couverture", "Couverture"), ("photo_dos", "dos", "4e de couverture (ISBN)")],
    "code_field": "isbn", "code_placeholder": "10 ou 13 chiffres, au dos près du code-barres",
    "lookup": books_lookup, "lookup_name": "Google Books / Open Library",
    "lookup_wins": ["pages", "editeur", "annee"],
    "no_ai": ["emplacement", "lu", "pret"],
    "aliases": {"auteur": ["auteurs", "author", "authors", "ecrivain"], "titre": ["title"], "editeur": ["publisher", "maison_d_edition"],
                "annee": ["year", "date", "date_de_publication"], "resume": ["description", "synopsis"]},
    "prompt": """Tu es un libraire expert, y compris en livres anciens. Tu reçois une ou deux photos d'un livre de ma bibliothèque : la couverture et/ou la 4e de couverture.
Lis attentivement tout le texte visible et remplis la fiche :
- titre, auteur, editeur, collection, annee, langue, format (Broché, Relié, Poche, Beau livre, Bande dessinée, Revue / magazine, Partition, Autre), genre
- isbn : les chiffres de l'ISBN (souvent au-dessus du code-barres), sans tirets ; pages si indiqué
- edition : mention d'édition originale, numéro de tirage… si visible
- etat : laisse vide sauf dégât visible ; estimation_basse_eur / estimation_haute_eur : prix d'occasion indicatif, nombre seul (plus élevé pour une édition ancienne ou rare)
- resume : 3 à 5 phrases sur le livre (sujet, intérêt), seulement si tu le connais
- notes : ce qui est illisible ou incertain ; identification_ia : une phrase sur ton niveau de confiance.
N'invente rien : laisse vide ce que tu ne peux pas lire ou savoir.""",
    "present_prompt": """Tu es un critique littéraire. Voici la fiche d'un livre de ma bibliothèque :
{fiche}
Écris en français un résumé de 4 à 6 phrases : sujet, thèmes, contexte de parution, place dans l'œuvre de l'auteur, intérêt de cette édition pour un collectionneur. Sans révéler la fin. Uniquement des faits dont tu es sûr ; si tu ne connais pas ce livre, dis-le en une phrase.
Réponds UNIQUEMENT en JSON : {{"texte": ""}}""",
    "complete_fields": ["resume", "genre", "estimation_basse_eur", "estimation_haute_eur"],
    "complete_wins": ["genre"],  # Open Library donne des sujets en anglais (« Fiction, Plague ») : l'IA met le genre en français
    "complete_prompt": """Tu es un libraire et critique littéraire. Voici la fiche d'un livre de ma bibliothèque :
{fiche}
Complète-la en français :
- resume : 4 à 6 phrases (sujet, thèmes, contexte de parution, place dans l'œuvre de l'auteur), sans révéler la fin. Si une description existe déjà en anglais, traduis-la et enrichis-la. Uniquement des faits dont tu es sûr ; si tu ne connais pas le livre, dis-le en une phrase.
- genre : un ou deux genres courts en français (ex. « Roman », « Essai, Philosophie », « Bande dessinée »).
- estimation_basse_eur / estimation_haute_eur : prix d'occasion indicatif pour cette édition, nombre seul.""",
    "add_help": "Photographiez la couverture et la 4e de couverture, ou tapez l'ISBN : l'app retrouve l'éditeur, l'année, le nombre de pages et le résumé.",
    "filters": ["genre", "format", "lu"],
    "search_hint": "titre, auteur, éditeur, emplacement…",
    "sort_keys": ["auteur", "titre", "annee", "editeur", "genre", "emplacement", "estimation_haute_eur"],
    "table_cols": ["auteur", "titre", "editeur", "annee", "genre", "format", "etat", "lu", "pret", "emplacement",
                   "estimation_basse_eur", "estimation_haute_eur", "resume"],
    "recap_by": ["genre", "format", "editeur", "lu"],
    "extra_metrics": [("Lus", lambda df: int((df["lu"] == "Oui").sum())),
                      ("Prêtés", lambda df: int((df["pret"].astype(str).str.strip() != "").sum()))],
    "ecoutes": False,
    "pdf_title": "Ma bibliothèque",
    "pdf": {"main": "titre", "sub": "auteur", "meta": ["editeur", "collection", "annee", "format", "isbn"],
            "small": ["etat", "edition", "emplacement"], "text": "resume", "photo": "photo_couverture",
            "list_cols": [("auteur", "Auteur"), ("titre", "Titre"), ("editeur", "Éditeur"), ("annee", "Année"),
                          ("format", "Format")]},
})
