"""Utilisateurs (réservé aux administrateurs) : créer, réinitialiser, supprimer des comptes."""
import pandas as pd
import streamlit as st

from auth import (EMAIL_RE, counts, create_user, delete_user, list_users, password_problem, set_admin, set_password,
                  suggest_password)
import mailer
from common import current_user

me = current_user()
if not me["admin"]:
    st.error("Page réservée aux administrateurs.")
    st.stop()

st.title("👥 Utilisateurs")
st.caption("Chaque utilisateur a ses propres collections ; personne ne voit celles des autres.")

try:
    users = list_users()
except Exception as e:
    st.error(f"Liste des comptes indisponible : {e}")
    st.stop()


def fmt(dt):
    return pd.to_datetime(str(dt), utc=True).tz_convert("Europe/Paris").strftime("%d/%m/%Y %H:%M") if dt else "—"


rows = []
for u in users:
    c = counts(str(u.id))
    rows.append({"E-mail": u.email, "Rôle": "Administrateur" if (u.app_metadata or {}).get("role") == "admin" else "Utilisateur",
                 "78 tours": c["disques"], "CD": c["cds"], "Livres": c["livres"],
                 "Créé le": fmt(u.created_at), "Dernière connexion": fmt(u.last_sign_in_at)})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

st.subheader("➕ Inviter quelqu'un")
if not mailer.configured():
    st.info("Pour envoyer les invitations automatiquement, ajoutez une section [smtp] dans les Secrets "
            "(voir README). En attendant, transmettez vous-même le mot de passe provisoire.")
if "new_pw" not in st.session_state:
    st.session_state.new_pw = suggest_password()
with st.form("new_user", clear_on_submit=False):
    email = st.text_input("E-mail de la personne")
    pw = st.text_input("Mot de passe provisoire", value=st.session_state.new_pw,
                       help="Communiquez-le à la personne : elle pourra le changer dans « Mon compte ».")
    is_admin = st.checkbox("Administrateur (peut gérer les comptes)")
    send_mail = st.checkbox("Envoyer l'invitation par e-mail", value=mailer.configured(), disabled=not mailer.configured())
    ok = st.form_submit_button("Créer le compte et inviter" if mailer.configured() else "Créer le compte", type="primary")
if ok:
    if not EMAIL_RE.match(email.strip()):
        st.error("E-mail invalide.")
    elif problem := password_problem(pw):
        st.error(problem)
    elif any((u.email or "").lower() == email.strip().lower() for u in users):
        st.error("Un compte existe déjà avec cet e-mail.")
    else:
        try:
            create_user(email, pw, is_admin)
            st.session_state.pop("new_pw", None)
            addr = email.strip().lower()
            if send_mail:
                try:
                    mailer.send_invitation(addr, pw, inviter=me["email"])
                    st.success(f"Compte créé et invitation envoyée à {addr}. "
                               "La personne choisira son mot de passe à la première connexion.")
                except Exception as e:
                    st.warning(f"Compte créé, mais l'e-mail n'a pas pu partir ({e}). "
                               f"Transmettez vous-même ce mot de passe provisoire : {pw}")
            else:
                st.success(f"Compte créé pour {addr}. Transmettez-lui l'adresse de l'application, "
                           f"son e-mail et ce mot de passe provisoire : {pw}")
        except Exception as e:
            st.error(f"Création impossible : {e}")

st.subheader("⚙️ Gérer un compte")
choice = st.selectbox("Compte", users, format_func=lambda u: u.email, index=None, placeholder="Choisissez un compte")
if choice:
    uid, is_me = str(choice.id), str(choice.id) == me["id"]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Réinitialiser le mot de passe**")
        new = st.text_input("Nouveau mot de passe", value=suggest_password(), key=f"reset_{uid}")
        mail_it = st.checkbox("L'envoyer par e-mail", value=mailer.configured(), disabled=not mailer.configured(),
                              key=f"mail_{uid}")
        if st.button("Réinitialiser", key=f"resetb_{uid}"):
            if problem := password_problem(new):
                st.error(problem)
            else:
                set_password(uid, new, must_change=True)
                if mail_it:
                    try:
                        mailer.send_new_password(choice.email, new)
                        st.success(f"Nouveau mot de passe provisoire envoyé à {choice.email}.")
                    except Exception as e:
                        st.warning(f"Mot de passe changé ({new}), mais l'e-mail n'a pas pu partir : {e}")
                else:
                    st.success(f"Nouveau mot de passe provisoire : {new}")
    with c2:
        st.markdown("**Rôle**")
        cur_admin = (choice.app_metadata or {}).get("role") == "admin"
        if is_me:
            st.caption("Vous ne pouvez pas retirer vos propres droits d'administrateur.")
        elif st.button("Retirer les droits d'administrateur" if cur_admin else "Nommer administrateur", key=f"role_{uid}"):
            set_admin(uid, not cur_admin)
            st.rerun()
        if st.button("Renvoyer l'invitation", key=f"reinv_{uid}", disabled=not mailer.configured(),
                     help="Crée un nouveau mot de passe provisoire et renvoie l'e-mail d'invitation"):
            tmp = suggest_password()
            set_password(uid, tmp, must_change=True)
            try:
                mailer.send_invitation(choice.email, tmp, inviter=me["email"])
                st.success(f"Invitation renvoyée à {choice.email}.")
            except Exception as e:
                st.warning(f"E-mail non envoyé ({e}). Mot de passe provisoire : {tmp}")
    with c3:
        st.markdown("**Supprimer le compte**")
        if is_me:
            st.caption("Vous ne pouvez pas supprimer votre propre compte.")
        else:
            sure = st.checkbox("Supprimer aussi toutes ses collections et photos (définitif)", key=f"sure_{uid}")
            if st.button("Supprimer", disabled=not sure, key=f"del_{uid}"):
                try:
                    delete_user(uid)
                    st.cache_data.clear()
                    st.success("Compte supprimé.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Suppression impossible : {e}")
