"""Comptes utilisateurs (Supabase Auth, e-mail + mot de passe, sur invitation)."""
import hmac
import re
import secrets as pysecrets
import time

import streamlit as st
from supabase import ClientOptions, create_client

TABLES = {"disques": ["photo_etiquette", "photo_face_b", "photo_pochette"],
          "cds": ["photo_recto", "photo_verso"],
          "livres": ["photo_couverture", "photo_dos"]}
BUCKET = "disques-photos"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def secret(section, key, default=""):
    try:
        return st.secrets[section][key]
    except Exception:
        return default


@st.cache_resource
def admin_client():
    """Client serveur (clé service_role) : ne sert jamais à ouvrir une session utilisateur."""
    return create_client(secret("supabase", "url"), secret("supabase", "service_role_key"))


def _fresh_client():
    """Client jetable pour vérifier un mot de passe, sans toucher au client partagé."""
    key = secret("supabase", "anon_key") or secret("supabase", "service_role_key")
    return create_client(secret("supabase", "url"), key,
                         options=ClientOptions(auto_refresh_token=False, persist_session=False))


def _as_dict(user):
    meta = getattr(user, "app_metadata", None) or {}
    return {"id": str(user.id), "email": user.email, "admin": meta.get("role") == "admin",
            "must_change": bool(meta.get("must_change"))}


def check_password(email, password):
    """Renvoie l'utilisateur si l'e-mail et le mot de passe sont bons, sinon None."""
    try:
        res = _fresh_client().auth.sign_in_with_password({"email": email.strip().lower(), "password": password})
        return _as_dict(res.user) if res and res.user else None
    except Exception:
        return None


def list_users():
    users = admin_client().auth.admin.list_users(page=1, per_page=1000)
    return sorted(users, key=lambda u: (u.email or "").lower())


def create_user(email, password, admin=False, must_change=True):
    """Crée un compte ; par défaut le mot de passe est provisoire et devra être changé à la première connexion."""
    res = admin_client().auth.admin.create_user({
        "email": email.strip().lower(), "password": password, "email_confirm": True,
        "app_metadata": {"role": "admin" if admin else "user", "must_change": must_change}})
    return res.user


def _meta(uid):
    try:
        return dict(admin_client().auth.admin.get_user_by_id(uid).user.app_metadata or {})
    except Exception:
        return {}


def _update_meta(uid, **changes):
    meta = _meta(uid)
    meta.update(changes)
    admin_client().auth.admin.update_user_by_id(uid, {"app_metadata": meta})


def set_password(uid, password, must_change=None):
    admin_client().auth.admin.update_user_by_id(uid, {"password": password})
    if must_change is not None:
        _update_meta(uid, must_change=must_change)


def set_admin(uid, admin):
    _update_meta(uid, role="admin" if admin else "user")


def forgot_password(email):
    """Envoie un mot de passe provisoire si le compte existe (au plus une fois par quart d'heure et par compte)."""
    import mailer
    email = email.strip().lower()
    user = next((u for u in list_users() if (u.email or "").lower() == email), None)
    if not user or not mailer.configured():
        return
    meta = dict(user.app_metadata or {})
    if time.time() - float(meta.get("last_reset", 0)) < 900:
        return
    pw = suggest_password()
    admin_client().auth.admin.update_user_by_id(str(user.id), {"password": pw})
    _update_meta(str(user.id), must_change=True, last_reset=time.time())
    mailer.send_new_password(email, pw, reason="forgot")


def delete_user(uid):
    """Supprime le compte, ses fiches et ses fichiers."""
    sb = admin_client()
    paths = []
    for table, cols in TABLES.items():
        rows = sb.table(table).select("*").eq("owner_id", uid).execute().data or []
        for r in rows:
            paths += [r[c] for c in cols if r.get(c)]
            for k in ("ecoute_face_a", "ecoute_face_b", "ecoutes"):
                v = str(r.get(k) or "")
                paths += re.findall(r'"url":\s*"([^"h][^"]*)"', v)  # fichiers audio déposés (pas les liens http)
        sb.table(table).delete().eq("owner_id", uid).execute()
    for i in range(0, len(paths), 100):
        try:
            sb.storage.from_(BUCKET).remove(paths[i:i + 100])
        except Exception:
            pass
    sb.auth.admin.delete_user(uid)


def counts(uid):
    sb = admin_client()
    return {t: sb.table(t).select("id", count="exact").eq("owner_id", uid).limit(1).execute().count or 0
            for t in TABLES}


def password_problem(pw, pw2=None):
    if len(pw or "") < 8:
        return "Le mot de passe doit faire au moins 8 caractères."
    if pw2 is not None and pw != pw2:
        return "Les deux mots de passe ne correspondent pas."
    return None


def suggest_password():
    return "-".join(pysecrets.token_urlsafe(4) for _ in range(3))


def _bootstrap():
    """Premier lancement : crée le compte administrateur et lui rattache les collections existantes."""
    st.info("**Première mise en route des comptes.** Créez votre compte administrateur. Toutes les collections "
            "déjà enregistrées (78 tours, CD, livres) vous seront rattachées.")
    with st.form("bootstrap"):
        old = st.text_input("Ancien mot de passe de l'application", type="password",
                            help="Celui de [app] password dans les Secrets : il prouve que vous êtes le propriétaire.")
        email = st.text_input("Votre e-mail")
        pw = st.text_input("Nouveau mot de passe (8 caractères minimum)", type="password")
        pw2 = st.text_input("Confirmez le mot de passe", type="password")
        ok = st.form_submit_button("Créer mon compte administrateur", type="primary")
    if not ok:
        return
    legacy = str(secret("app", "password"))
    if not legacy or not hmac.compare_digest(old.encode(), legacy.encode()):
        time.sleep(1)
        st.error("Ancien mot de passe incorrect.")
        return
    if not EMAIL_RE.match(email.strip()):
        st.error("E-mail invalide.")
        return
    problem = password_problem(pw, pw2)
    if problem:
        st.error(problem)
        return
    try:
        user = create_user(email, pw, admin=True, must_change=False)
        sb = admin_client()
        for table in TABLES:
            sb.table(table).update({"owner_id": str(user.id)}).is_("owner_id", "null").execute()
        st.session_state.user = _as_dict(user)
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Création impossible : {e}")


def login_gate():
    """Affiche la connexion tant que personne n'est connecté ; renvoie l'utilisateur connecté."""
    if st.session_state.get("user"):
        return st.session_state.user
    st.title("🗂️ Mes collections")
    st.caption("78 tours · CDthèque · Bibliothèque")
    try:
        no_users = len(admin_client().auth.admin.list_users(page=1, per_page=1)) == 0
    except Exception as e:
        st.error("Connexion à Supabase impossible. Vérifiez [supabase] url et service_role_key dans les Secrets.")
        st.code(str(e))
        st.stop()
    if no_users:
        _bootstrap()
        st.stop()
    with st.form("login"):
        email = st.text_input("E-mail")
        pw = st.text_input("Mot de passe", type="password")
        ok = st.form_submit_button("Se connecter", type="primary")
    if ok:
        user = check_password(email, pw)
        if user:
            st.session_state.user = user
            st.rerun()
        time.sleep(1)  # freine les essais en rafale
        st.error("E-mail ou mot de passe incorrect.")
    import mailer
    if mailer.configured():
        with st.expander("Mot de passe oublié ?"):
            with st.form("forgot", clear_on_submit=True):
                f_email = st.text_input("Votre e-mail")
                sent = st.form_submit_button("Recevoir un mot de passe provisoire")
            if sent:
                try:
                    forgot_password(f_email)
                except Exception:
                    pass
                # même réponse que le compte existe ou non : on ne révèle pas qui est inscrit
                st.success("Si un compte existe pour cette adresse, un e-mail vient de lui être envoyé.")
        st.caption("Pas encore de compte ? Demandez une invitation à l'administrateur.")
    else:
        st.caption("Pas encore de compte ou mot de passe oublié ? Demandez à l'administrateur de l'application.")
    st.stop()
