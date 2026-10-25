import base64, hmac, io, json, re, time, uuid
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageOps
from supabase import create_client

st.set_page_config(page_title="Ma collection de 78 tours", page_icon="💿", layout="wide")

BUCKET = "disques-photos"
ETATS = ["Très bon état", "Bon état", "État moyen", "Abîmé"]
POCHETTES = ["Oui", "Non", "À confirmer"]
FIELDS = ["titre_face_a", "interprete_face_a", "titre_face_b", "interprete_face_b", "orchestre", "auteurs",
          "label_marque", "reference_disque", "annee", "estimation_basse_eur", "estimation_haute_eur",
          "notes", "identification_ia"]
LONG_FIELDS = ("notes", "identification_ia")
LABELS = {
    "titre_face_a": "Titre face A", "interprete_face_a": "Interprète face A",
    "titre_face_b": "Titre face B", "interprete_face_b": "Interprète face B",
    "orchestre": "Orchestre", "auteurs": "Auteurs", "label_marque": "Marque / label",
    "reference_disque": "Référence", "annee": "Année",
    "estimation_basse_eur": "Estimation basse (€)", "estimation_haute_eur": "Estimation haute (€)",
    "notes": "Notes", "identification_ia": "Identification IA",
    "etat": "État", "pochette": "Pochette", "created_at": "Date d'ajout", "id": "Identifiant",
    "Face A": "Face A", "Face B": "Face B",
}
PHOTOS = [("photo_etiquette", "etiquette", "Face A"), ("photo_face_b", "face_b", "Face B"),
          ("photo_pochette", "pochette", "Pochette")]
IMG_TYPES = ["jpg", "jpeg", "png", "webp"]


def secret(section, key, default=""):
    try:
        return st.secrets[section][key]
    except Exception:
        return default


# ---------------------------------------------------------------- Connexion
password = secret("app", "password")
if not password:
    st.error("Configuration manquante : ajoutez [app] password dans les Secrets Streamlit.")
    st.stop()
if not st.session_state.get("auth_ok"):
    st.title("💿 Ma collection de disques 78 tours")
    with st.form("login"):
        entered = st.text_input("Mot de passe", type="password")
        ok = st.form_submit_button("Se connecter", type="primary")
    if ok:
        if hmac.compare_digest(entered.encode(), str(password).encode()):
            st.session_state.auth_ok = True
            st.rerun()
        time.sleep(1)  # freine les essais en rafale
        st.error("Mot de passe incorrect.")
    st.stop()

GROQ_KEY = secret("groq", "api_key")
GROQ_MODEL = secret("groq", "model", "qwen/qwen3.8-27b")


@st.cache_resource
def db():
    return create_client(secret("supabase", "url"), secret("supabase", "service_role_key"))


@st.cache_data(ttl=300, show_spinner=False)
def load_records():
    return db().table("disques").select("*").order("created_at", desc=True).execute().data or []


def refresh():
    load_records.clear()
    st.rerun()


try:
    sb = db()
    records = load_records()
except Exception as e:
    st.error("Connexion Supabase impossible. Vérifiez les Secrets et exécutez supabase_schema.sql.")
    st.code(str(e))
    st.stop()


# ---------------------------------------------------------------- Utilitaires
def jpg_bytes(upload):
    """Convertit une photo en JPEG redressé (orientation EXIF des téléphones) et réduit."""
    im = Image.open(io.BytesIO(upload.getvalue()))
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((1600, 1600))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=82, optimize=True)
    return b.getvalue()


def upload_photo(path, upload):
    sb.storage.from_(BUCKET).upload(path, jpg_bytes(upload), {"content-type": "image/jpeg", "upsert": "true"})


@st.cache_data(ttl=3000, show_spinner=False)
def signed_url(path):
    res = sb.storage.from_(BUCKET).create_signed_url(path, 3600)
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


def face(r, side):
    return " — ".join(str(r.get(k) or "").strip() for k in (f"titre_face_{side}", f"interprete_face_{side}")
                      if str(r.get(k) or "").strip())


def prepare(recs):
    df = pd.DataFrame(recs)
    for c in FIELDS + ["etat", "pochette", "created_at", "id"] + [p[0] for p in PHOTOS]:
        if c not in df.columns:
            df[c] = ""
    df = df.fillna("")
    df["Face A"] = df.apply(lambda r: face(r, "a"), axis=1)
    df["Face B"] = df.apply(lambda r: face(r, "b"), axis=1)
    df["_basse"] = df["estimation_basse_eur"].apply(euro_number)
    df["_haute"] = df["estimation_haute_eur"].apply(euro_number)
    # Une seule estimation saisie → elle sert de borne basse ET haute (évite un total bas > total haut).
    df["_basse"], df["_haute"] = df["_basse"].fillna(df["_haute"]), df["_haute"].fillna(df["_basse"])
    df["_annee"] = df["annee"].apply(year_number)
    return df


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


def export_frame(df):
    cols = ["titre_face_a", "interprete_face_a", "titre_face_b", "interprete_face_b", "orchestre", "auteurs",
            "label_marque", "reference_disque", "annee", "etat", "pochette", "estimation_basse_eur",
            "estimation_haute_eur", "notes", "created_at"]
    return df[cols].rename(columns=LABELS)


# ---------------------------------------------------------------- IA (Groq)
PROMPT = """Tu examines les deux photos d'un même disque 78 tours. La PREMIÈRE photo montre la FACE A et la DEUXIÈME photo montre la FACE B. Lis séparément les deux étiquettes et retranscris fidèlement les titres et interprètes de chaque face. Ne devine jamais un texte illisible : indique-le dans notes. Renseigne aussi le label, la référence (numéro de catalogue), l'année si lisible, l'orchestre et les auteurs. Donne une estimation indicative de revente pour le disque complet en euros (nombres seuls dans estimation_basse_eur et estimation_haute_eur), sans la présenter comme une cote garantie. Dans identification_ia, résume en une phrase ton niveau de confiance. Sois très concis : chaque champ doit contenir une valeur courte, aucune explication hors JSON. Réponds uniquement en JSON valide avec les champs: titre_face_a, titre_face_b, interprete_face_a, interprete_face_b, orchestre, auteurs, label_marque, reference_disque, annee, estimation_basse_eur, estimation_haute_eur, notes, identification_ia. Les valeurs sont des chaînes de caractères."""


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def groq_error(response):
    try:
        return response.json().get("error", {}).get("message", response.text)
    except Exception:
        return response.text


def identify(upload_a, upload_b):
    if not GROQ_KEY:
        raise ValueError("Clé Groq manquante dans les Secrets Streamlit. Ajoutez [groq] puis api_key.")
    img = lambda u: "data:image/jpeg;base64," + base64.b64encode(jpg_bytes(u)).decode("ascii")
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "text", "text": "PHOTO 1 — FACE A"},
            {"type": "image_url", "image_url": {"url": img(upload_a)}},
            {"type": "text", "text": "PHOTO 2 — FACE B"},
            {"type": "image_url", "image_url": {"url": img(upload_b)}},
        ]}],
        "temperature": 0.2,
        "max_completion_tokens": 900,
        "reasoning_effort": "none",
        "response_format": {"type": "json_object"},
    }
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    response = None
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=(15, 180))
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt == 2:
                raise RuntimeError("Groq ne répond pas après trois tentatives. Réessayez plus tard.") from e
            time.sleep(3 * (attempt + 1))
            continue
        if response.status_code == 429 and attempt < 2:
            m = re.search(r"try again in ([0-9.]+)s", groq_error(response), re.IGNORECASE)
            time.sleep(min(60, max(2, int(float(m.group(1))) + 2)) if m else 20)
            continue
        if response.status_code >= 500 and attempt < 2:
            time.sleep(3)
            continue
        break
    if response is None or response.status_code >= 400:
        code = response.status_code if response is not None else "réseau"
        detail = groq_error(response) if response is not None else "Aucune réponse"
        raise RuntimeError(f"Groq API ({code}) : {detail}")
    try:
        data = parse_json(response.json()["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise RuntimeError("Groq n'a pas renvoyé de JSON exploitable. Réessayez avec des photos plus nettes.") from e
    return {f: ("" if data.get(f) is None else str(data.get(f)).strip()) for f in FIELDS}


# ---------------------------------------------------------------- Formulaire commun
def field_inputs(source, prefix):
    vals = {}
    left, right = st.columns(2)
    for i, f in enumerate(FIELDS):
        with (left if i < 7 else right):
            current = str(source.get(f) or "")
            if f in LONG_FIELDS:
                vals[f] = st.text_area(LABELS[f], value=current, height=90, key=f"{prefix}_{f}")
            else:
                vals[f] = st.text_input(LABELS[f], value=current, key=f"{prefix}_{f}")
    return vals


def duplicates(ref, exclude_id=None):
    ref = (ref or "").strip().casefold()
    if not ref:
        return []
    return [r for r in records if str(r.get("reference_disque") or "").strip().casefold() == ref
            and r.get("id") != exclude_id]


# ---------------------------------------------------------------- En-tête
head, logout = st.columns([6, 1])
with head:
    st.title("💿 Ma collection de disques 78 tours")
    st.caption(f"Photos et fiches conservées dans Supabase · identification par Groq ({GROQ_MODEL}).")
with logout:
    st.write("")
    if st.button("🔄 Actualiser"):
        refresh()
    if st.button("Se déconnecter"):
        st.session_state.clear()
        st.rerun()

tabs = st.tabs(["➕ Ajouter un disque", "📚 Catalogue", "📊 Récapitulatif", "⬇️ Exporter"])

# ---------------------------------------------------------------- Ajout
with tabs[0]:
    n = st.session_state.setdefault("form_nonce", 0)  # change après chaque enregistrement → formulaire vidé
    if st.session_state.pop("just_saved", False):
        st.success("Disque enregistré avec les deux faces. Vous pouvez photographier le suivant.")
    st.write("Photographiez les deux étiquettes du même disque. L'IA les analyse ensemble pour créer une seule fiche.")
    c1, c2, c3 = st.columns(3)
    with c1:
        face_a_photo = st.file_uploader("📷 Face A (obligatoire)", type=IMG_TYPES, key=f"fa_{n}")
        if face_a_photo:
            st.image(face_a_photo, width=260)
    with c2:
        face_b_photo = st.file_uploader("📷 Face B (obligatoire)", type=IMG_TYPES, key=f"fb_{n}")
        if face_b_photo:
            st.image(face_b_photo, width=260)
    with c3:
        cover_photo = st.file_uploader("Pochette (facultatif)", type=IMG_TYPES, key=f"cv_{n}")
        if cover_photo:
            st.image(cover_photo, width=260)

    # Si les photos changent, l'ancienne analyse IA n'est plus valable.
    photo_sig = (face_a_photo.file_id if face_a_photo else None, face_b_photo.file_id if face_b_photo else None)
    if st.session_state.get("ai_sig") not in (None, photo_sig):
        st.session_state.pop("ai_result", None)
        st.session_state.pop("ai_sig", None)

    if not GROQ_KEY:
        st.info("Ajoutez [groq] api_key dans les Secrets pour activer l'identification automatique. "
                "Vous pouvez quand même saisir la fiche à la main.")
    if st.button("🔎 Analyser les deux faces", type="primary",
                 disabled=not (GROQ_KEY and face_a_photo and face_b_photo)):
        try:
            with st.spinner("Analyse des deux faces… cela peut prendre jusqu'à une minute."):
                st.session_state.ai_result = identify(face_a_photo, face_b_photo)
                st.session_state.ai_sig = photo_sig
                st.session_state.ai_round = st.session_state.get("ai_round", 0) + 1
        except Exception as e:
            st.error(f"Erreur IA : {e}")

    result = st.session_state.get("ai_result", {})
    if result:
        st.success("Analyse terminée : relisez et corrigez les champs ci-dessous avant d'enregistrer.")
        dups = duplicates(result.get("reference_disque"))
        if dups:
            st.warning(f"⚠️ La référence « {result.get('reference_disque')} » existe déjà dans la collection "
                       f"({face(dups[0], 'a') or 'sans titre'}). Doublon possible.")

    with st.form(f"new_record_{n}"):
        st.subheader("Fiche du disque")
        vals = field_inputs(result, f"new{n}_{st.session_state.get('ai_round', 0)}")
        s1, s2 = st.columns(2)
        with s1:
            state = st.selectbox("État", ETATS)
        with s2:
            cover = st.radio("Pochette présente ?", POCHETTES, index=0 if cover_photo else 2, horizontal=True)
        submitted = st.form_submit_button("💾 Enregistrer le disque", type="primary")
    if submitted:
        if not face_a_photo or not face_b_photo:
            st.error("Ajoutez les photos des faces A et B.")
        elif not any(vals[f].strip() for f in ("titre_face_a", "titre_face_b", "reference_disque")):
            st.error("Renseignez au moins un titre ou la référence du disque.")
        else:
            try:
                with st.spinner("Enregistrement…"):
                    did = str(uuid.uuid4())
                    paths = {"photo_etiquette": f"{did}/etiquette.jpg", "photo_face_b": f"{did}/face_b.jpg",
                             "photo_pochette": f"{did}/pochette.jpg" if cover_photo else None}
                    upload_photo(paths["photo_etiquette"], face_a_photo)
                    upload_photo(paths["photo_face_b"], face_b_photo)
                    if cover_photo:
                        upload_photo(paths["photo_pochette"], cover_photo)
                    row = {"id": did, "created_at": datetime.now().astimezone().isoformat(),
                           **{k: v.strip() for k, v in vals.items()}, "etat": state, "pochette": cover, **paths}
                    sb.table("disques").insert(row).execute()
                for k in ("ai_result", "ai_sig"):
                    st.session_state.pop(k, None)
                st.session_state.form_nonce = n + 1
                st.session_state.just_saved = True
                refresh()
            except Exception as e:
                st.error(f"Enregistrement impossible : {e}")

# ---------------------------------------------------------------- Catalogue
with tabs[1]:
    if not records:
        st.info("Aucun disque enregistré.")
    else:
        df = prepare(records)
        f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
        with f1:
            q = st.text_input("🔍 Rechercher", placeholder="titre, interprète, orchestre, auteur, référence…")
        with f2:
            labels = sorted(x for x in df["label_marque"].unique() if str(x).strip())
            sel_labels = st.multiselect("Marque / label", labels)
        with f3:
            sel_etats = st.multiselect("État", ETATS)
        with f4:
            sel_poch = st.multiselect("Pochette", POCHETTES)
        if q:
            cols = FIELDS + ["Face A", "Face B"]
            mask = df[cols].astype(str).apply(lambda c: c.str.contains(q, case=False, regex=False, na=False))
            df = df[mask.any(axis=1)]
        if sel_labels:
            df = df[df["label_marque"].isin(sel_labels)]
        if sel_etats:
            df = df[df["etat"].isin(sel_etats)]
        if sel_poch:
            df = df[df["pochette"].isin(sel_poch)]

        sort_keys = ["created_at", "Face A", "Face B", "titre_face_a", "interprete_face_a", "titre_face_b",
                     "interprete_face_b", "orchestre", "auteurs", "label_marque", "reference_disque", "annee",
                     "etat", "estimation_basse_eur", "estimation_haute_eur"]
        o1, o2 = st.columns([3, 2])
        with o1:
            sort_by = st.selectbox("Trier par", sort_keys, format_func=LABELS.get, key="catalog_sort_by")
        with o2:
            desc = st.toggle("Ordre décroissant", value=(sort_by == "created_at"), key=f"desc_{sort_by}")
        sort_series = {
            "annee": df["_annee"], "estimation_basse_eur": df["_basse"], "estimation_haute_eur": df["_haute"],
            "created_at": pd.to_datetime(df["created_at"], errors="coerce", utc=True),
            "etat": df["etat"].map({e: i for i, e in enumerate(ETATS)}),
        }.get(sort_by, df[sort_by].astype(str).str.casefold().where(lambda x: x != ""))
        df = df.assign(_s=sort_series).sort_values("_s", ascending=not desc, na_position="last", kind="stable")

        st.caption(f"{len(df)} disque(s) affiché(s) sur {len(records)} · valeur estimée "
                   f"{fmt_eur(df['_basse'].sum(min_count=1))} – {fmt_eur(df['_haute'].sum(min_count=1))}")
        visible = ["Face A", "Face B", "orchestre", "label_marque", "reference_disque", "annee", "etat",
                   "pochette", "estimation_basse_eur", "estimation_haute_eur"]
        event = st.dataframe(df[visible].rename(columns=LABELS), width="stretch", hide_index=True,
                             on_select="rerun", selection_mode="single-row", key="catalog_table")
        st.caption("Cliquez sur une ligne pour afficher la fiche détaillée.")

        rows = event.selection.rows if event and hasattr(event, "selection") else []
        if rows and rows[0] < len(df):
            chosen = df.iloc[rows[0]].to_dict()
            cid = chosen["id"]
            st.divider()
            st.subheader(f"💿 {chosen['Face A'] or 'Titre inconnu'}")
            if chosen["Face B"]:
                st.caption(f"Face B : {chosen['Face B']}")
            info, pics = st.columns([2, 3])
            with info:
                for f in FIELDS + ["etat", "pochette"]:
                    if f not in ("titre_face_a", "interprete_face_a", "titre_face_b", "interprete_face_b"):
                        st.markdown(f"**{LABELS[f]} :** {chosen.get(f) or '—'}")
            with pics:
                pcols = st.columns(3)
                for (key, _, caption), pc in zip(PHOTOS, pcols):
                    if chosen.get(key):
                        try:
                            pc.image(signed_url(chosen[key]), caption=caption, width="stretch")
                        except Exception:
                            pc.caption(f"{caption} : photo indisponible")

            with st.expander("✏️ Modifier cette fiche"):
                with st.form(f"edit_{cid}"):
                    edit_vals = field_inputs(chosen, f"edit_{cid}")
                    e1, e2 = st.columns(2)
                    with e1:
                        edit_etat = st.selectbox("État", ETATS, index=ETATS.index(chosen["etat"]) if chosen["etat"] in ETATS else 0)
                    with e2:
                        edit_poch = st.radio("Pochette présente ?", POCHETTES, horizontal=True,
                                             index=POCHETTES.index(chosen["pochette"]) if chosen["pochette"] in POCHETTES else 2)
                    st.markdown("**Remplacer une photo (facultatif)**")
                    pc = st.columns(3)
                    new_photos = {key: pc[i].file_uploader(cap, type=IMG_TYPES, key=f"rp_{key}_{cid}")
                                  for i, (key, _, cap) in enumerate(PHOTOS)}
                    save_edit = st.form_submit_button("Enregistrer les modifications", type="primary")
                if save_edit:
                    try:
                        upd = {k: v.strip() for k, v in edit_vals.items()} | {"etat": edit_etat, "pochette": edit_poch}
                        for key, fname, _ in PHOTOS:
                            if new_photos[key]:
                                path = chosen.get(key) or f"{cid}/{fname}.jpg"
                                upload_photo(path, new_photos[key])
                                upd[key] = path
                                signed_url.clear()
                        sb.table("disques").update(upd).eq("id", cid).execute()
                        st.toast("Modifications enregistrées.")
                        refresh()
                    except Exception as e:
                        st.error(f"Modification impossible : {e}")

            with st.expander("🗑️ Supprimer cette fiche"):
                st.warning("Cette action est définitive : la fiche et ses photos seront effacées.")
                sure = st.checkbox("Je confirme vouloir supprimer ce disque", key=f"sure_{cid}")
                if st.button("Supprimer définitivement", disabled=not sure, key=f"del_{cid}"):
                    try:
                        paths = [chosen[k] for k, _, _ in PHOTOS if chosen.get(k)]
                        if paths:
                            try:
                                sb.storage.from_(BUCKET).remove(paths)
                            except Exception:
                                pass
                        sb.table("disques").delete().eq("id", cid).execute()
                        st.toast("Disque supprimé.")
                        refresh()
                    except Exception as e:
                        st.error(f"Suppression impossible : {e}")

# ---------------------------------------------------------------- Récapitulatif
with tabs[2]:
    if not records:
        st.info("Aucun disque enregistré : le récapitulatif apparaîtra dès le premier ajout.")
    else:
        recap = prepare(records)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Disques", len(recap))
        m2.metric("Valeur estimée basse", fmt_eur(recap["_basse"].sum(min_count=1)))
        m3.metric("Valeur estimée haute", fmt_eur(recap["_haute"].sum(min_count=1)))
        m4.metric("Avec pochette", int((recap["pochette"] == "Oui").sum()))
        st.caption("Montants indicatifs saisis ou proposés par l'IA : ce n'est ni une expertise ni une garantie de prix.")

        def counts(col, empty, title):
            s = recap[col].replace("", empty).value_counts()
            return s.rename_axis(title).reset_index(name="Nombre")

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("#### État des disques")
            etats = counts("etat", "Non renseigné", "État")
            st.bar_chart(etats, x="État", y="Nombre", horizontal=True)
        with g2:
            st.markdown("#### Par décennie")
            dec = recap["_annee"].dropna().astype(int) // 10 * 10
            if len(dec):
                dc = (dec.astype(str) + "s").value_counts().sort_index().rename_axis("Décennie").reset_index(name="Nombre")
                st.bar_chart(dc, x="Décennie", y="Nombre")
            else:
                st.info("Aucune année renseignée.")
            if recap["_annee"].isna().any():
                st.caption(f"{int(recap['_annee'].isna().sum())} disque(s) sans année lisible.")

        g3, g4 = st.columns(2)
        with g3:
            st.markdown("#### Par marque / label")
            st.dataframe(counts("label_marque", "Non renseigné", "Marque / label"), width="stretch", hide_index=True)
        with g4:
            st.markdown("#### Disques les plus estimés")
            top = recap.dropna(subset=["_haute"]).nlargest(10, "_haute")
            if len(top):
                st.dataframe(top[["Face A", "label_marque", "estimation_basse_eur", "estimation_haute_eur"]]
                             .rename(columns=LABELS), width="stretch", hide_index=True)
            else:
                st.info("Aucune estimation renseignée.")

        incomplete = recap[(recap["titre_face_a"] == "") | (recap["reference_disque"] == "") | (recap["_annee"].isna())]
        if len(incomplete):
            with st.expander(f"📝 {len(incomplete)} fiche(s) à compléter (titre, référence ou année manquant)"):
                st.dataframe(incomplete[["Face A", "Face B", "label_marque", "reference_disque", "annee"]]
                             .rename(columns=LABELS), width="stretch", hide_index=True)

# ---------------------------------------------------------------- Export
with tabs[3]:
    if not records:
        st.info("Ajoutez un disque pour commencer.")
    else:
        out = export_frame(prepare(records))
        stamp = datetime.now().strftime("%Y-%m-%d")
        st.write(f"{len(out)} disques à exporter.")
        x1, x2 = st.columns(2)
        with x1:
            try:
                st.download_button("📗 Télécharger en Excel (.xlsx)", to_excel(out), f"collection_78_tours_{stamp}.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
            except ImportError:
                st.caption("Ajoutez openpyxl à requirements.txt pour l'export Excel.")
        with x2:
            st.download_button("📄 Télécharger en CSV", out.to_csv(index=False, sep=";").encode("utf-8-sig"),
                               f"collection_78_tours_{stamp}.csv", "text/csv")
        st.caption("Le CSV utilise le point-virgule comme séparateur, pour s'ouvrir directement dans Excel en français.")
