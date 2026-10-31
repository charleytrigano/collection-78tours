"""Point d'entrée : connexion par mot de passe puis menu des collections."""
import hmac
import time

import streamlit as st

st.set_page_config(page_title="Mes collections", page_icon="🗂️", layout="wide")


def secret(section, key, default=""):
    try:
        return st.secrets[section][key]
    except Exception:
        return default


password = secret("app", "password")
if not password:
    st.error("Configuration manquante : ajoutez [app] password dans les Secrets Streamlit.")
    st.stop()
if not st.session_state.get("auth_ok"):
    st.title("🗂️ Mes collections")
    st.caption("78 tours · CDthèque · Bibliothèque")
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

pages = [
    st.Page("page_78tours.py", title="Disques 78 tours", icon="💿", url_path="78-tours", default=True),
    st.Page("page_cd.py", title="CDthèque", icon="📀", url_path="cdtheque"),
    st.Page("page_livres.py", title="Bibliothèque", icon="📚", url_path="bibliotheque"),
]
st.navigation(pages).run()
