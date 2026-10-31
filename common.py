"""Outils partagés par les collections (CDthèque, Bibliothèque) : connexion, photos, IA, export, écoute."""
import base64, io, json, re, time, unicodedata
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps
from supabase import create_client

BUCKET = "disques-photos"
IMG_TYPES = ["jpg", "jpeg", "png", "webp"]
UA = {"User-Agent": "mes-collections/1.0 (+https://github.com/charleytrigano/collection-78tours)"}


def secret(section, key, default=""):
    try:
        return st.secrets[section][key]
    except Exception:
        return default



@st.cache_resource
def db():
    return create_client(secret("supabase", "url"), secret("supabase", "service_role_key"))



def jpg_bytes(upload, size=1600):
    """Convertit une photo en JPEG redressé (orientation EXIF des téléphones) et réduit."""
    im = Image.open(io.BytesIO(upload.getvalue()))
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((size, size))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=82, optimize=True)
    return b.getvalue()



@st.cache_data(ttl=3000, show_spinner=False)
def signed_url(path):
    res = db().storage.from_(BUCKET).create_signed_url(path, 3600)
    return res.get("signedURL") or res.get("signedUrl") if isinstance(res, dict) else getattr(res, "signed_url", None)


def euro_number(value):
    """'12', '12,50 €', 'env. 15', '10-15' → premier nombre trouvé."""
    m = re.search(r"\d+(?:[.,]\d+)?", str(value or "").replace(" ", "").replace(" ", ""))
    return float(m.group().replace(",", ".")) if m else None


def year_number(value):
    m = re.search(r"(18|19|20)\d{2}", str(value or ""))
    return int(m.group()) if m else None


def fmt_eur(x):
    return "—" if x is None or pd.isna(x) else f"{x:,.0f} €".replace(",", " ")



def to_excel(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Collection")
        ws = xw.sheets["Collection"]
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col[:200])
            ws.column_dimensions[col[0].column_letter].width = min(50, max(10, width + 2))
        ws.freeze_panes = "A2"
    return out.getvalue()



PROVIDERS = {
    # Chaque modèle Gemini gratuit a son propre quota journalier : on bascule sur le suivant quand l'un est épuisé.
    "Gemini (Google)": {"section": "gemini",
                        "models": ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
                        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                        "extra": {"max_tokens": 4000, "reasoning_effort": "low"}},
    "Groq": {"section": "groq", "models": ["qwen/qwen3.8-27b"],
             "url": "https://api.groq.com/openai/v1/chat/completions",
             "extra": {"max_completion_tokens": 1500, "reasoning_effort": "none",
                       "response_format": {"type": "json_object"}}},
}


def _models(p):
    custom = secret(p["section"], "model")
    return ([custom] if custom else []) + [m for m in p["models"] if m != custom]


AVAILABLE = {name: {**p, "key": secret(p["section"], "api_key"), "models": _models(p), "model": _models(p)[0]}
             for name, p in PROVIDERS.items() if secret(p["section"], "api_key")}


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def _norm(k):
    k = unicodedata.normalize("NFKD", str(k)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", k).strip("_")



def api_error(response):
    try:
        j = response.json()
        j = j[0] if isinstance(j, list) else j
        return j.get("error", {}).get("message", response.text)
    except Exception:
        return response.text


class QuotaExhausted(Exception):
    pass


def _call(p, model, payload, provider):
    """Un appel ; réessaie seulement les erreurs passagères (réseau, 5xx, limite par minute)."""
    headers = {"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = requests.post(p["url"], headers=headers, json={**payload, "model": model}, timeout=(15, 180))
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt == 2:
                raise RuntimeError(f"{provider} ne répond pas après trois tentatives. Réessayez plus tard.") from e
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 429:
            detail = api_error(r)
            # Quota du jour épuisé : inutile d'attendre, chaque nouvel essai consommerait du quota.
            if re.search(r"per ?day|perday|daily|exceeded your current quota", detail, re.IGNORECASE):
                raise QuotaExhausted(detail)
            m = re.search(r"(?:try again|retry) in ([0-9.]+)s", detail, re.IGNORECASE)
            wait = float(m.group(1)) if m else 20
            if attempt < 2 and wait <= 60:
                time.sleep(max(2, wait + 1))
                continue
            raise QuotaExhausted(detail)
        if r.status_code >= 500 and attempt < 1:  # une seule nouvelle tentative, puis modèle suivant
            time.sleep(2)
            continue
        return r
    return r


def _ask_one(provider, content):
    """Essaie chaque modèle du fournisseur ; passe au suivant si quota épuisé, modèle absent ou serveur saturé."""
    p = AVAILABLE[provider]
    payload = {"messages": [{"role": "user", "content": content}], "temperature": 0.1, **p["extra"]}
    skipped, reasons = [], set()
    for model in p["models"]:
        try:
            response = _call(p, model, payload, provider)
        except QuotaExhausted:
            skipped.append(model)
            reasons.add("quota")
            continue
        if response.status_code in (400, 404) and re.search(r"model|not found|not supported", api_error(response), re.I):
            skipped.append(model)  # modèle retiré ou indisponible pour ce compte
            continue
        if response.status_code >= 500:
            skipped.append(model)  # « high demand » / surcharge passagère : on tente le modèle suivant
            reasons.add("surcharge")
            continue
        break
    else:
        if reasons == {"quota"}:
            why = "quota gratuit épuisé pour aujourd'hui (réinitialisation vers 9 h, heure de Paris)"
        elif "surcharge" in reasons:
            why = "serveurs saturés pour le moment, réessayez dans quelques minutes"
        else:
            why = "aucun modèle disponible"
        raise RuntimeError(f"{provider} : {why} ({', '.join(skipped)}).")
    if response.status_code >= 400:
        raise RuntimeError(f"{provider} ({response.status_code}) : {api_error(response)}")
    st.session_state.ai_model = f"{provider} · {model}"
    try:
        return response.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError, ValueError):
        return response.text


def ask_ai(provider, content, max_tokens=None):
    """Demande à l'IA choisie ; si elle est indisponible, bascule automatiquement sur l'autre IA configurée."""
    errors = []
    for prov in [provider] + [x for x in AVAILABLE if x != provider]:
        try:
            raw = _ask_one(prov, content)
            if prov != provider:
                st.toast(f"{provider} indisponible : analyse faite avec {prov}.")
            return raw
        except RuntimeError as e:
            errors.append(str(e))
    raise RuntimeError(" / ".join(errors))



def yt_id(url):
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{11})", url or "")
    return m.group(1) if m else None


def clean_url(url):
    """Nettoie un lien : YouTube réduit à la seule vidéo (supprime &list=RD…, &start_radio…)."""
    url = (url or "").strip()
    vid = yt_id(url)
    if vid:
        t = re.search(r"[?&]t=(\d+)", url)
        return f"https://www.youtube.com/watch?v={vid}" + (f"&t={t.group(1)}" if t else "")
    return url


def kind_of(src):
    if yt_id(src):
        return "YouTube"
    for dom, name in (("youtube.com", "YouTube"), ("spotify.com", "Spotify"), ("deezer.com", "Deezer"),
                      ("archive.org", "Internet Archive"), ("soundcloud.com", "SoundCloud"), ("gallica", "Gallica")):
        if dom in (src or ""):
            return name
    return "Lien" if str(src).startswith("http") else "Mon enregistrement"


def play(item, height=None):
    """Lit une écoute : vidéo YouTube, Spotify / Deezer intégrés, MP3 direct ou fichier déposé."""
    src = item["url"]
    vid = yt_id(src)
    sp = re.search(r"open\.spotify\.com/(?:intl-\w+/)?(track|album|playlist)/(\w+)", src)
    dz = re.search(r"deezer\.com/(?:\w{2}/)?(track|album|playlist)/(\d+)", src)
    if vid:
        st.video(f"https://www.youtube.com/watch?v={vid}")
    elif sp:
        components.iframe(f"https://open.spotify.com/embed/{sp.group(1)}/{sp.group(2)}", height=152)
    elif dz:
        components.iframe(f"https://widget.deezer.com/widget/auto/{dz.group(1)}/{dz.group(2)}", height=152)
    elif src.startswith("http") and re.search(r"\.(mp3|ogg|wav|m4a|flac|aac)(\?|$)|archive\.org/download/", src, re.I):
        st.audio(src)
    elif src.startswith("http"):
        st.link_button("Ouvrir le lien ↗", src)  # page de chaîne, playlist… : pas de lecteur possible
    else:
        try:
            st.audio(signed_url(src))
        except Exception:
            st.caption("Fichier audio indisponible.")



def ecoutes(value):
    """Liste d'écoutes [{"url", "nom", "ajout"}] stockée en JSON (accepte aussi un lien seul)."""
    if isinstance(value, list):
        return value
    v = str(value or "").strip()
    if not v:
        return []
    if v.startswith("["):
        try:
            return [i for i in json.loads(v) if isinstance(i, dict) and i.get("url")]
        except json.JSONDecodeError:
            return []
    return [{"url": v, "nom": ""}]


def flatten(data):
    """Aplatit une réponse IA (clés normalisées, listes jointes)."""
    if isinstance(data, list) and data:
        data = data[0]
    flat = {}

    def walk(d, prefix=""):
        for k, v in (d or {}).items():
            key = _norm(f"{prefix}_{k}" if prefix else k)
            if isinstance(v, dict):
                walk(v, key)
            elif v not in (None, "", []):
                flat[key] = "\n".join(map(str, v)) if isinstance(v, list) else str(v).strip()
    walk(data if isinstance(data, dict) else {})
    return flat


def price_bounds(lo, hi):
    """Normalise deux estimations en nombres seuls ; « 10-15 € » donne 10 et 15."""
    def nums(x):
        return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", str(x or "").replace(" ", ""))]
    a, b = nums(lo), nums(hi)
    lo_v = min(a) if a else (min(b) if b else None)
    hi_v = max(b) if b else (max(a) if a else None)
    f = lambda v: "" if v is None else f"{v:g}"
    return f(lo_v), f(hi_v)


def img_data_url(upload, size=2000):
    return "data:image/jpeg;base64," + base64.b64encode(jpg_bytes(upload, size)).decode("ascii")
