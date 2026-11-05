"""Mon compte : changer son mot de passe."""
import streamlit as st

from auth import check_password, counts, password_problem, set_password
from common import current_user

user = current_user()
st.title("👤 Mon compte")
st.markdown(f"**E-mail :** {user['email']}" + ("  \n**Rôle :** administrateur" if user["admin"] else ""))
try:
    c = counts(user["id"])
    a, b, d = st.columns(3)
    a.metric("Disques 78 tours", c["disques"])
    b.metric("CD", c["cds"])
    d.metric("Livres", c["livres"])
except Exception:
    pass

st.subheader("Changer mon mot de passe")
with st.form("change_pw", clear_on_submit=True):
    cur = st.text_input("Mot de passe actuel", type="password")
    pw = st.text_input("Nouveau mot de passe (8 caractères minimum)", type="password")
    pw2 = st.text_input("Confirmez le nouveau mot de passe", type="password")
    ok = st.form_submit_button("Changer le mot de passe", type="primary")
if ok:
    if not check_password(user["email"], cur):
        st.error("Mot de passe actuel incorrect.")
    elif problem := password_problem(pw, pw2):
        st.error(problem)
    else:
        try:
            set_password(user["id"], pw)
            st.success("Mot de passe changé.")
        except Exception as e:
            st.error(f"Changement impossible : {e}")
