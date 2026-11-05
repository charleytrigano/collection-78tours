"""Point d'entrée : connexion par compte puis menu des collections."""
import streamlit as st

from auth import login_gate

st.set_page_config(page_title="Mes collections", page_icon="🗂️", layout="wide")

user = login_gate()

with st.sidebar:
    st.caption(f"Connecté : **{user['email']}**" + (" · administrateur" if user["admin"] else ""))
    if st.button("Se déconnecter", key="logout_sidebar"):
        st.session_state.clear()
        st.rerun()

if user.get("must_change"):  # mot de passe provisoire : on ne montre que « Mon compte » tant qu'il n'est pas changé
    st.navigation([st.Page("page_compte.py", title="Mon compte", icon="👤", url_path="compte")]).run()
    st.stop()

pages = {
    "Mes collections": [
        st.Page("page_78tours.py", title="Disques 78 tours", icon="💿", url_path="78-tours", default=True),
        st.Page("page_cd.py", title="CDthèque", icon="📀", url_path="cdtheque"),
        st.Page("page_livres.py", title="Bibliothèque", icon="📚", url_path="bibliotheque"),
    ],
    "Compte": [st.Page("page_compte.py", title="Mon compte", icon="👤", url_path="compte")]
    + ([st.Page("page_utilisateurs.py", title="Utilisateurs", icon="👥", url_path="utilisateurs")] if user["admin"] else []),
}
st.navigation(pages).run()
