import base64, io, json, uuid
from datetime import datetime
import pandas as pd
import streamlit as st
import requests
from PIL import Image
from supabase import create_client

st.set_page_config(page_title="Ma collection de 78 tours", page_icon="💿", layout="wide")

def secret(section, key):
    try: return st.secrets[section][key]
    except Exception: return ""

password = secret("app", "password")
if not password:
    st.error("Configuration manquante : ajoutez [app] password dans les Secrets Streamlit.")
    st.stop()
if not st.session_state.get("auth_ok"):
    st.title("💿 Ma collection de disques 78 tours")
    entered = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter", type="primary"):
        if entered == password:
            st.session_state.auth_ok = True
            st.rerun()
        st.error("Mot de passe incorrect.")
    st.stop()

@st.cache_resource
def db():
    return create_client(secret("supabase","url"), secret("supabase","service_role_key"))
try:
    sb = db()
    records = sb.table("disques").select("*").order("created_at", desc=True).execute().data or []
except Exception as e:
    st.error("Connexion Supabase impossible. Vérifiez les Secrets et exécutez supabase_schema.sql.")
    st.code(str(e)); st.stop()

st.title("💿 Ma collection de disques 78 tours")
st.caption("Les photos et les fiches sont conservées dans Supabase. L’identification utilise Gemini, avec un quota gratuit limité.")
api_key = secret("gemini","api_key")

def jpg_bytes(upload):
    im = Image.open(upload).convert("RGB"); im.thumbnail((1200,1200))
    b = io.BytesIO(); im.save(b, "JPEG", quality=78, optimize=True); return b.getvalue()

def identify(upload):
    if not api_key:
        raise ValueError("Clé Gemini manquante dans les Secrets Streamlit ([gemini] api_key).")
    raw = jpg_bytes(upload)
    prompt = """Lis cette étiquette de disque 78 tours. Transcris fidèlement les éléments visibles et ne devine pas les éléments illisibles. Donne une estimation indicative de revente en euros, sans présenter cela comme une cote garantie. Réponds uniquement en JSON avec les champs: titre_face_a, titre_face_b, interprete_face_a, interprete_face_b, orchestre, auteurs, label_marque, reference_disque, annee, estimation_basse_eur, estimation_haute_eur, notes, identification_ia."""
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(raw).decode("ascii")}}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    # Une seconde tentative peut suffire en cas de lenteur temporaire du service.
    last_error = None
    for attempt in range(2):
        try:
            response = requests.post(url, params={"key": api_key}, json=payload, timeout=(15, 180))
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_error = e
            if attempt == 1:
                raise RuntimeError("Gemini ne répond toujours pas après deux tentatives. Attendez une minute puis réessayez, idéalement avec une photo plus rapprochée et nette.") from last_error
    if response.status_code >= 400:
        try: detail = response.json().get("error", {}).get("message", response.text)
        except Exception: detail = response.text
        raise RuntimeError(f"Gemini API ({response.status_code}) : {detail}")
    try:
        return json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise RuntimeError("Gemini n'a pas renvoyé de réponse JSON exploitable. Réessayez avec une photo plus nette.") from e

tabs = st.tabs(["➕ Ajouter un disque", "📚 Catalogue", "⬇️ Exporter", "📊 État récapitulatif"])
fields = ["titre_face_a","interprete_face_a","titre_face_b","interprete_face_b","orchestre","auteurs","label_marque","reference_disque","annee","estimation_basse_eur","estimation_haute_eur","notes","identification_ia"]
with tabs[0]:
    c1,c2 = st.columns(2)
    with c1: label_photo = st.file_uploader("Photo nette de l'étiquette", type=["jpg","jpeg","png","webp"], key="label")
    with c2: cover_photo = st.file_uploader("Photo de la pochette (facultatif)", type=["jpg","jpeg","png","webp"], key="cover")
    state = st.selectbox("État", ["Très bon état","Bon état","État moyen","Abîmé"])
    cover = st.radio("Pochette présente ?", ["Oui","Non","À confirmer"], horizontal=True)
    if label_photo:
        st.image(label_photo, width=300)
        if st.button("🔎 Identifier gratuitement avec Gemini", type="primary", disabled=not api_key):
            try:
                with st.spinner("Analyse de l'étiquette…"): st.session_state.ai_result = identify(label_photo)
            except Exception as e: st.error(f"Erreur IA : {e}")
    result = st.session_state.get("ai_result", {})
    with st.form("new_record"):
        st.subheader("Vérifiez les informations avant l'enregistrement")
        vals = {}
        a,b = st.columns(2)
        for i,f in enumerate(fields):
            with (a if i < 7 else b):
                default = str(result.get(f,"") or "")
                vals[f] = st.text_area(f.replace("_"," ").capitalize(), value=default, height=70 if f in ("notes","identification_ia") else 40) if f in ("notes","identification_ia") else st.text_input(f.replace("_"," ").capitalize(), value=default)
        if st.form_submit_button("Enregistrer le disque", type="primary"):
            if not label_photo: st.error("Ajoutez une photo d'étiquette.")
            else:
                try:
                    did = str(uuid.uuid4())
                    p1 = f"{did}/etiquette.jpg"; sb.storage.from_("disques-photos").upload(p1, jpg_bytes(label_photo), {"content-type":"image/jpeg","upsert":"true"})
                    p2 = None
                    if cover_photo:
                        p2 = f"{did}/pochette.jpg"; sb.storage.from_("disques-photos").upload(p2, jpg_bytes(cover_photo), {"content-type":"image/jpeg","upsert":"true"})
                    payload = {"id":did, "created_at":datetime.now().astimezone().isoformat(), **vals, "etat":state, "pochette":cover, "photo_etiquette":p1, "photo_pochette":p2}
                    sb.table("disques").insert(payload).execute()
                    st.session_state.pop("ai_result",None); st.success("Disque enregistré."); st.rerun()
                except Exception as e: st.error(f"Enregistrement impossible : {e}")
with tabs[1]:
    if records:
        df = pd.DataFrame(records).fillna("")
        q = st.text_input("Rechercher un titre, interprète, orchestre, auteur ou référence")
        if q: df = df[df.astype(str).apply(lambda c:c.str.contains(q,case=False,na=False)).any(axis=1)]
        cols = ["titre_face_a","titre_face_b","interprete_face_a","interprete_face_b","orchestre","auteurs","label_marque","reference_disque","annee","etat","pochette","estimation_basse_eur","estimation_haute_eur"]
        st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True, hide_index=True)
        options = df.to_dict("records")
        if options:
            chosen = st.selectbox("Détail du disque", options, format_func=lambda r:f"{r.get('titre_face_a') or 'Titre inconnu'} — {r.get('interprete_face_a') or 'Interprète inconnu'}", key="chosen")
            for f in fields + ["etat","pochette"]:
                st.write(f"**{f.replace('_',' ').capitalize()} :** {chosen.get(f) or '—'}")
            for key,caption in [("photo_etiquette","Étiquette"),("photo_pochette","Pochette")]:
                path = chosen.get(key)
                if path:
                    try: st.image(sb.storage.from_("disques-photos").create_signed_url(path,3600)["signedURL"], caption=caption, width=300)
                    except Exception: pass
            with st.expander("Supprimer cette fiche"):
                st.warning("Cette action est définitive.")
                if st.button("Confirmer la suppression", key="del"):
                    for path in [chosen.get("photo_etiquette"),chosen.get("photo_pochette")]:
                        if path:
                            try: sb.storage.from_("disques-photos").remove([path])
                            except Exception: pass
                    sb.table("disques").delete().eq("id",chosen["id"]).execute(); st.rerun()
    else: st.info("Aucun disque enregistré.")
with tabs[2]:
    if records:
        df = pd.DataFrame(records).fillna("")
        st.download_button("Télécharger le catalogue CSV pour Excel", df.to_csv(index=False).encode("utf-8-sig"), "ma_collection_78_tours.csv", "text/csv")
    else: st.info("Ajoutez un disque pour commencer.")

with tabs[3]:
    st.subheader("État récapitulatif de la collection")
    if not records:
        st.info("Aucun disque enregistré : le récapitulatif apparaîtra dès le premier ajout.")
    else:
        recap = pd.DataFrame(records).fillna("")
        def euro_number(value):
            if value is None: return None
            s = str(value).strip().replace("€", "").replace(" ", "").replace(",", ".")
            try: return float(s) if s else None
            except (TypeError, ValueError): return None

        for col in ["estimation_basse_eur", "estimation_haute_eur"]:
            if col not in recap.columns:
                recap[col] = None
            recap[col + "_num"] = recap[col].apply(euro_number)
        total = len(recap)
        basse = recap["estimation_basse_eur_num"].sum(min_count=1)
        haute = recap["estimation_haute_eur_num"].sum(min_count=1)
        c1, c2, c3 = st.columns(3)
        c1.metric("Nombre de disques", total)
        c2.metric("Valeur estimée basse", "Non renseignée" if pd.isna(basse) else f"{basse:,.0f} €".replace(",", " "))
        c3.metric("Valeur estimée haute", "Non renseignée" if pd.isna(haute) else f"{haute:,.0f} €".replace(",", " "))
        st.caption("Les montants sont des estimations indicatives saisies ou proposées par l’IA, et non une expertise ni une garantie de prix de vente.")

        st.markdown("#### État des disques")
        etats = recap["etat"].replace("", "Non renseigné").value_counts().rename_axis("État").reset_index(name="Nombre")
        st.dataframe(etats, use_container_width=True, hide_index=True)

        st.markdown("#### Présence des pochettes")
        pochettes = recap["pochette"].replace("", "À confirmer").value_counts().rename_axis("Pochette").reset_index(name="Nombre")
        st.dataframe(pochettes, use_container_width=True, hide_index=True)

        st.markdown("#### Répartition par marque / label")
        marques = recap["label_marque"].replace("", "Non renseigné").value_counts().rename_axis("Marque / label").reset_index(name="Nombre")
        st.dataframe(marques, use_container_width=True, hide_index=True)

        st.markdown("#### Répartition par décennie")
        annees = pd.to_numeric(recap.get("annee", pd.Series(index=recap.index, dtype="object")).astype(str).str.extract(r"(\\d{4})", expand=False), errors="coerce")
        decades = (annees // 10 * 10).dropna().astype(int).astype(str) + "s"
        if len(decades):
            decade_counts = decades.value_counts().sort_index().rename_axis("Décennie").reset_index(name="Nombre")
            st.dataframe(decade_counts, use_container_width=True, hide_index=True)
        else:
            st.info("Les années ne sont pas encore renseignées pour les disques.")

        st.markdown("#### Liste récapitulative")
        display_cols = ["titre_face_a", "interprete_face_a", "titre_face_b", "interprete_face_b", "label_marque", "reference_disque", "annee", "etat", "pochette", "estimation_basse_eur", "estimation_haute_eur"]
        summary = recap[[col for col in display_cols if col in recap.columns]].copy()
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.download_button("Télécharger l’état récapitulatif (CSV pour Excel)", summary.to_csv(index=False).encode("utf-8-sig"), "etat_recapitulatif_78_tours.csv", "text/csv")
