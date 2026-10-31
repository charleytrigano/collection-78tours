"""CDthèque."""
import requests

from collection_generic import run
from common import UA

ETATS = ["", "Neuf / scellé", "Très bon état", "Bon état", "État moyen", "Abîmé"]
FORMATS = ["", "CD", "Double CD", "Coffret", "CD single", "SACD", "Vinyle 33 tours", "Vinyle 45 tours", "Cassette",
           "DVD musical", "Autre"]
MB = "https://musicbrainz.org/ws/2"


def _ms(ms):
    try:
        s = int(ms) // 1000
        return f" ({s // 60}:{s % 60:02d})"
    except (TypeError, ValueError):
        return ""


def musicbrainz(code):
    """Recherche un album par code-barres sur MusicBrainz (gratuit, sans clé)."""
    r = requests.get(f"{MB}/release/", params={"query": f"barcode:{code}", "fmt": "json", "limit": 1},
                     headers=UA, timeout=20)
    r.raise_for_status()
    rels = r.json().get("releases", [])
    if not rels:
        return {}
    rel = requests.get(f"{MB}/release/{rels[0]['id']}", headers=UA, timeout=20,
                       params={"inc": "recordings+artist-credits+labels+genres+release-groups", "fmt": "json"}).json()
    media = rel.get("media", [])
    pistes = []
    for i, m in enumerate(media, 1):
        prefix = f"CD{i} – " if len(media) > 1 else ""
        for t in m.get("tracks", []):
            pistes.append(f"{prefix}{t.get('number') or t.get('position')}. {t.get('title', '')}{_ms(t.get('length'))}")
    li = (rel.get("label-info") or [{}])[0]
    genres = sorted(rel.get("genres", []) + rel.get("release-group", {}).get("genres", []),
                    key=lambda g: -g.get("count", 0))
    fmt = media[0].get("format", "") if media else ""
    return {
        "artiste": "".join(a.get("name", "") + a.get("joinphrase", "") for a in rel.get("artist-credit", [])),
        "titre": rel.get("title", ""),
        "annee": (rel.get("release-group", {}).get("first-release-date") or rel.get("date") or "")[:4],
        "label": (li.get("label") or {}).get("name", ""),
        "reference": li.get("catalog-number", "") or "",
        "code_barres": rel.get("barcode") or code,
        "nb_disques": str(len(media)) if media else "",
        "format": ("Double CD" if len(media) == 2 and "CD" in fmt else "Coffret" if len(media) > 2 else
                   "CD" if "CD" in fmt else ""),
        "genre": genres[0]["name"].capitalize() if genres else "",
        "pistes": "\n".join(pistes),
        "_cover": f"https://coverartarchive.org/release/{rel['id']}/front-500",
    }


run({
    "table": "cds", "prefix": "cd", "icon": "📀",
    "title": "📀 Ma CDthèque", "caption": "Photo du boîtier → fiche complète (pistes, label, année) grâce à l'IA et MusicBrainz.",
    "item": "CD", "item_pl": "CD", "un": "un CD", "le": "le CD", "du": "du CD", "ce": "ce CD",
    "fields": [
        ("artiste", "Artiste", "text"), ("titre", "Titre de l'album", "text"), ("label", "Label", "text"),
        ("annee", "Année", "text"), ("genre", "Genre", "text"), ("format", "Format", "select", FORMATS),
        ("reference", "Référence (n° catalogue)", "text"), ("code_barres", "Code-barres (EAN)", "text"),
        ("nb_disques", "Nombre de disques", "text"), ("etat", "État", "select", ETATS),
        ("emplacement", "Emplacement (meuble, étagère…)", "text"),
        ("estimation_basse_eur", "Estimation basse (€)", "text"), ("estimation_haute_eur", "Estimation haute (€)", "text"),
        ("pistes", "Pistes", "long"), ("presentation", "Présentation", "long"), ("notes", "Notes", "long"),
        ("identification_ia", "Identification IA", "long"),
    ],
    "main": "titre", "sub": "artiste", "text_art": "la présentation", "text_art_de": "de la présentation", "text_field": "presentation",
    "photos": [("photo_recto", "recto", "Pochette (recto)"), ("photo_verso", "verso", "Dos du boîtier (pistes, code-barres)")],
    "code_field": "code_barres", "code_placeholder": "13 chiffres sous le code-barres, au dos",
    "lookup": musicbrainz, "lookup_name": "MusicBrainz",
    "lookup_wins": ["pistes", "annee", "label", "reference", "nb_disques"],
    "no_ai": ["emplacement"],
    "aliases": {"artiste": ["artist", "interprete", "groupe"], "titre": ["album", "title"], "label": ["maison_de_disques"],
                "code_barres": ["ean", "barcode", "upc"], "pistes": ["tracklist", "tracks", "liste_des_pistes"],
                "annee": ["year", "date"]},
    "prompt": """Tu es un disquaire expert. Tu reçois une ou deux photos d'un CD (ou disque) de ma collection : la pochette et/ou le dos du boîtier.
Lis attentivement tout le texte visible et remplis la fiche :
- artiste, titre (de l'album), label, annee, genre, format (CD, Double CD, Coffret, CD single, SACD, Vinyle 33 tours, Vinyle 45 tours, Cassette, DVD musical, Autre)
- reference : numéro de catalogue de l'éditeur ; code_barres : les chiffres EAN/UPC sous le code-barres (sans espaces)
- nb_disques ; pistes : une piste par ligne « 1. Titre (durée) » si lisibles au dos
- etat : laisse vide sauf dégât visible ; estimation_basse_eur / estimation_haute_eur : prix de revente d'occasion indicatif, nombre seul
- presentation : 3 à 5 phrases sur l'album (contexte, style, place dans la carrière de l'artiste) seulement si tu es sûr
- notes : ce qui est illisible ou incertain ; identification_ia : une phrase sur ton niveau de confiance.
N'invente rien : laisse vide ce que tu ne peux pas lire ou savoir.""",
    "present_prompt": """Tu es un critique musical. Voici la fiche d'un album de ma CDthèque :
{fiche}
Écris en français une présentation de 4 à 6 phrases : contexte de sortie, style, musiciens notables, accueil, morceaux marquants, intérêt pour un collectionneur. Uniquement des faits dont tu es sûr ; si tu ne connais pas cet album, dis-le en une phrase.
Réponds UNIQUEMENT en JSON : {{"texte": ""}}""",
    "complete_fields": ["presentation", "genre", "estimation_basse_eur", "estimation_haute_eur"],
    "complete_prompt": """Tu es un critique musical et disquaire. Voici la fiche d'un album de ma CDthèque :
{fiche}
Complète-la en français :
- presentation : 4 à 6 phrases (contexte de sortie, style, musiciens notables, accueil, morceaux marquants). Uniquement des faits dont tu es sûr ; si tu ne connais pas l'album, dis-le en une phrase.
- genre : un genre court en français si absent (ex. « Jazz », « Rock », « Chanson française »).
- estimation_basse_eur / estimation_haute_eur : prix d'occasion indicatif pour ce pressage, nombre seul.""",
    "add_help": "Photographiez la pochette et le dos du boîtier, ou tapez le code-barres : l'app retrouve les pistes, le label et l'année.",
    "filters": ["genre", "format", "etat"],
    "search_hint": "artiste, album, label, morceau…",
    "sort_keys": ["artiste", "titre", "annee", "genre", "label", "format", "emplacement", "estimation_haute_eur"],
    "table_cols": ["artiste", "titre", "annee", "genre", "label", "format", "etat", "emplacement",
                   "estimation_basse_eur", "estimation_haute_eur", "Écoutes", "presentation"],
    "recap_by": ["genre", "format", "label", "etat"],
    "ecoutes": True,
    "pdf_title": "Ma CDthèque",
    "pdf": {"main": "titre", "sub": "artiste", "meta": ["label", "annee", "format", "genre", "reference"],
            "small": ["etat", "emplacement"], "text": "presentation", "photo": "photo_recto",
            "list_cols": [("artiste", "Artiste"), ("titre", "Album"), ("annee", "Année"), ("label", "Label"),
                          ("format", "Format")]},
})
