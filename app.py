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
st.caption("Les photos et les fiches sont conservées dans Supabase. L’identification des deux faces utilise Groq (modèle Qwen vision).")
api_key = secret("groq","api_key")

def jpg_bytes(upload):
    im = Image.open(upload).convert("RGB"); im.thumbnail((1200,1200))
    b = io.BytesIO(); im.save(b, "JPEG", quality=78, optimize=True); return b.getvalue()

def identify(upload_a, upload_b):
    if not api_key:
        raise ValueError("Clé Groq manquante dans les Secrets Streamlit. Ajoutez [groq] puis api_key.")
    raw_a = jpg_bytes(upload_a)
    raw_b = jpg_bytes(upload_b)
    prompt = """Tu examines les deux photos d'un même disque 78 tours. La PREMIÈRE photo montre la FACE A et la DEUXIÈME photo montre la FACE B. Lis séparément les deux étiquettes et retranscris fidèlement les titres et interprètes de chaque face. Ne devine jamais un texte illisible : indique-le dans notes. Renseigne aussi le label, la référence, l'année si lisible, l'orchestre et les auteurs. Donne une estimation indicative de revente pour le disque complet en euros, sans la présenter comme une cote garantie. Réponds uniquement en JSON valide avec les champs: titre_face_a, titre_face_b, interprete_face_a, interprete_face_b, orchestre, auteurs, label_marque, reference_disque, annee, estimation_basse_eur, estimation_haute_eur, notes, identification_ia. Les valeurs peuvent être des chaînes de caractères."""
    image_a = "data:image/jpeg;base64," + base64.b64encode(raw_a).decode("ascii")
    image_b = "data:image/jpeg;base64," + base64.b64encode(raw_b).decode("ascii")
    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "text", "text": "PHOTO 1 — FACE A"},
            {"type": "image_url", "image_url": {"url": image_a}},
            {"type": "text", "text": "PHOTO 2 — FACE B"},
            {"type": "image_url", "image_url": {"url": image_b}}
        ]}],
        "temperature": 0.2,
        "max_completion_tokens": 1600,
        "response_format": {"type": "json_object"}
    }
    url = "https://api.groq.com/openai/v1/chat/completions"
    last_error = None
    for attempt in range(2):
        try:
            response = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload, timeout=(15, 180))
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_error = e
            if attempt == 1:
                raise RuntimeError("Groq ne répond toujours pas après deux tentatives. Réessayez avec des photos plus rapprochées et nettes.") from last_error
    if response.status_code >= 400:
        try: detail = response.json().get("error", {}).get("message", response.text)
        except Exception: detail = response.text
        if response.status_code == 429:
            raise RuntimeError(f"Quota Groq temporairement dépassé : {detail}")
        raise RuntimeError(f"Groq API ({response.status_code}) : {detail}")
    try:
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise RuntimeError("Groq n'a pas renvoyé de réponse JSON exploitable. Réessayez avec des photos plus nettes.") from e

tabs = st.tabs(["➕ Ajouter un disque", "📚 Catalogue", "⬇️ Exporter", "📊 État récapitulatif"])
fields = ["titre_face_a","interprete_face_a","titre_face_b","interprete_face_b","orchestre","auteurs","label_marque","reference_disque","annee","estimation_basse_eur","estimation_haute_eur","notes","identification_ia"]
with tabs[0]:
    st.write("Photographiez les deux étiquettes du même disque. L’IA les analysera ensemble pour créer une seule fiche.")
    c1,c2 = st.columns(2)
    with c1: face_a_photo = st.file_uploader("📷 Photo de la face A (obligatoire)", type=["jpg","jpeg","png","webp"], key="face_a_photo")
    with c2: face_b_photo = st.file_uploader("📷 Photo de la face B (obligatoire)", type=["jpg","jpeg","png","webp"], key="face_b_photo")
    cover_photo = st.file_uploader("Photo de la pochette (facultatif)", type=["jpg","jpeg","png","webp"], key="cover")
    if face_a_photo:
        with c1: st.image(face_a_photo, caption="Face A", width=280)
    if face_b_photo:
        with c2: st.image(face_b_photo, caption="Face B", width=280)
    state = st.selectbox("État", ["Très bon état","Bon état","État moyen","Abîmé"])
    cover = st.radio("Pochette présente ?", ["Oui","Non","À confirmer"], horizontal=True)
    if st.button("🔎 Analyser les deux faces avec Gemini", type="primary", disabled=(not api_key or not face_a_photo or not face_b_photo)):
        try:
            with st.spinner("Analyse des deux faces… cela peut prendre un peu de temps."):
                st.session_state.ai_result = identify(face_a_photo, face_b_photo)
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
            if not face_a_photo or not face_b_photo:
                st.error("Ajoutez les photos des faces A et B.")
            else:
                try:
                    did = str(uuid.uuid4())
                    p1 = f"{did}/etiquette.jpg"
                    sb.storage.from_("disques-photos").upload(p1, jpg_bytes(face_a_photo), {"content-type":"image/jpeg","upsert":"true"})
                    p_face_b = f"{did}/face_b.jpg"
                    sb.storage.from_("disques-photos").upload(p_face_b, jpg_bytes(face_b_photo), {"content-type":"image/jpeg","upsert":"true"})
                    p2 = None
                    if cover_photo:
                        p2 = f"{did}/pochette.jpg"
                        sb.storage.from_("disques-photos").upload(p2, jpg_bytes(cover_photo), {"content-type":"image/jpeg","upsert":"true"})
                    payload = {"id":did, "created_at":datetime.now().astimezone().isoformat(), **vals, "etat":state, "pochette":cover, "photo_etiquette":p1, "photo_face_b":p_face_b, "photo_pochette":p2}
                    sb.table("disques").insert(payload).execute()
                    st.session_state.pop("ai_result",None); st.success("Disque enregistré avec les deux faces."); st.rerun()
                except Exception as e: st.error(f"Enregistrement impossible : {e}")
with tabs[1]:
    if records:
        df = pd.DataFrame(records).fillna("")
        q = st.text_input("Rechercher un titre, interprète, orchestre, auteur ou référence")
        if q: df = df[df.astype(str).apply(lambda c:c.str.contains(q,case=False,na=False)).any(axis=1)]
        df["Face A"] = df.apply(lambda r: " — ".join(str(x) for x in [r.get("titre_face_a", ""), r.get("interprete_face_a", "")] if str(x or "").strip()), axis=1)
        df["Face B"] = df.apply(lambda r: " — ".join(str(x) for x in [r.get("titre_face_b", ""), r.get("interprete_face_b", "")] if str(x or "").strip()), axis=1)
        cols = ["Face A", "Face B", "orchestre", "auteurs", "label_marque", "reference_disque", "annee", "etat", "pochette", "estimation_basse_eur", "estimation_haute_eur"]
        visible_cols = [col for col in cols if col in df.columns]
        st.markdown("#### Trier le catalogue")
        sort_labels = {
            "Face A": "Face A — titre / interprète",
            "Face B": "Face B — titre / interprète",
            "titre_face_a": "Titre face A",
            "interprete_face_a": "Interprète face A",
            "titre_face_b": "Titre face B",
            "interprete_face_b": "Interprète face B",
            "orchestre": "Orchestre",
            "auteurs": "Auteurs",
            "label_marque": "Marque / label",
            "reference_disque": "Référence",
            "annee": "Année",
            "etat": "État",
            "pochette": "Pochette",
            "estimation_basse_eur": "Estimation basse (€)",
            "estimation_haute_eur": "Estimation haute (€)",
            "notes": "Notes",
            "identification_ia": "Identification IA",
            "created_at": "Date d'ajout",
            "id": "Identifiant"
        }
        sort_keys = [key for key in sort_labels if key in df.columns]
        sort_c1, sort_c2 = st.columns([3, 2])
        with sort_c1:
            sort_by = st.selectbox("Trier par", sort_keys, format_func=lambda key: sort_labels[key], key="catalog_sort_by")
        with sort_c2:
            sort_order = st.radio("Ordre", ["Croissant (A → Z / plus petit au plus grand)", "Décroissant (Z → A / plus grand au plus petit)"], horizontal=False, key="catalog_sort_order")
        if sort_by in ("annee", "estimation_basse_eur", "estimation_haute_eur"):
            df["_sort_value"] = pd.to_numeric(df[sort_by].astype(str).str.replace("€", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
        elif sort_by == "created_at":
            df["_sort_value"] = pd.to_datetime(df[sort_by], errors="coerce", utc=True)
        else:
            df["_sort_value"] = df[sort_by].astype(str).str.casefold()
        df = df.sort_values("_sort_value", ascending=sort_order.startswith("Croissant"), na_position="last", kind="stable").drop(columns=["_sort_value"])
        st.dataframe(df[visible_cols], use_container_width=True, hide_index=True)
        options = df.to_dict("records")
        if options:
            chosen = st.selectbox("Détail du disque", options, format_func=lambda r:f"{r.get('titre_face_a') or 'Titre inconnu'} — {r.get('interprete_face_a') or 'Interprète inconnu'}", key="chosen")
            for f in fields + ["etat","pochette"]:
                st.write(f"**{f.replace('_',' ').capitalize()} :** {chosen.get(f) or '—'}")
            for key,caption in [("photo_etiquette","Face A"),("photo_face_b","Face B"),("photo_pochette","Pochette")]:
                path = chosen.get(key)
                if path:
                    try: st.image(sb.storage.from_("disques-photos").create_signed_url(path,3600)["signedURL"], caption=caption, width=300)
                    except Exception: pass
            with st.expander("✏️ Modifier cette fiche"):
                with st.form("edit_record_form"):
                    edit_vals = {}
                    left, right = st.columns(2)
                    for i, field_name in enumerate(fields):
                        with (left if i < 7 else right):
                            current = str(chosen.get(field_name) or "")
                            if field_name in ("notes", "identification_ia"):
                                edit_vals[field_name] = st.text_area(field_name.replace("_", " ").capitalize(), value=current, height=80, key="edit_" + field_name)
                            else:
                                edit_vals[field_name] = st.text_input(field_name.replace("_", " ").capitalize(), value=current, key="edit_" + field_name)
                    etats_edit = ["Très bon état", "Bon état", "État moyen", "Abîmé"]
                    etat_actuel = chosen.get("etat") or "Très bon état"
                    edit_etat = st.selectbox("État du disque", etats_edit, index=etats_edit.index(etat_actuel) if etat_actuel in etats_edit else 0)
                    pochettes_edit = ["Oui", "Non", "À confirmer"]
                    pochette_actuelle = chosen.get("pochette") or "À confirmer"
                    edit_pochette = st.radio("Pochette présente ?", pochettes_edit, index=pochettes_edit.index(pochette_actuelle) if pochette_actuelle in pochettes_edit else 2, horizontal=True)
                    save_edit = st.form_submit_button("Enregistrer les modifications", type="primary")
                if save_edit:
                    try:
                        edit_vals["etat"] = edit_etat
                        edit_vals["pochette"] = edit_pochette
                        sb.table("disques").update(edit_vals).eq("id", chosen["id"]).execute()
                        st.success("Modifications enregistrées.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Modification impossible : {e}")
            with st.expander("Supprimer cette fiche"):
                st.warning("Cette action est définitive.")
                if st.button("Confirmer la suppression", key="del"):
                    for path in [chosen.get("photo_etiquette"),chosen.get("photo_face_b"),chosen.get("photo_pochette")]:
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
        recap["Face A"] = recap.apply(lambda r: " — ".join(str(x) for x in [r.get("titre_face_a", ""), r.get("interprete_face_a", "")] if str(x or "").strip()), axis=1)
        recap["Face B"] = recap.apply(lambda r: " — ".join(str(x) for x in [r.get("titre_face_b", ""), r.get("interprete_face_b", "")] if str(x or "").strip()), axis=1)
        display_cols = ["Face A", "Face B", "label_marque", "reference_disque", "annee", "etat", "pochette", "estimation_basse_eur", "estimation_haute_eur"]
        summary = recap[[col for col in display_cols if col in recap.columns]].copy()
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.download_button("Télécharger l’état récapitulatif (CSV pour Excel)", summary.to_csv(index=False).encode("utf-8-sig"), "etat_recapitulatif_78_tours.csv", "text/csv")
