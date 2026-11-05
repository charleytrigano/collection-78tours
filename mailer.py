"""Envoi d'e-mails (invitations, mots de passe) par SMTP : Gmail, Brevo, OVH…"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

import streamlit as st


def _smtp(key, default=""):
    try:
        return st.secrets["smtp"][key]
    except Exception:
        return default


def configured():
    return bool(_smtp("server") and _smtp("user") and _smtp("password"))


def app_url():
    try:
        url = st.secrets["app"]["url"]
    except Exception:
        url = ""
    if not url:
        try:
            url = st.context.url or ""
        except Exception:
            url = ""
    return url.split("?")[0].rstrip("/") if url else ""


def send(to, subject, text, html=None):
    msg = EmailMessage()
    sender = _smtp("sender") or _smtp("user")
    msg["From"] = formataddr((_smtp("sender_name", "Mes collections"), sender))
    msg["To"] = to
    msg["Subject"] = subject
    if _smtp("reply_to"):
        msg["Reply-To"] = _smtp("reply_to")
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    port = int(_smtp("port", 465))
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(_smtp("server"), port, context=ctx, timeout=30) as s:
            s.login(_smtp("user"), _smtp("password"))
            s.send_message(msg)
    else:
        with smtplib.SMTP(_smtp("server"), port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(_smtp("user"), _smtp("password"))
            s.send_message(msg)


def _html(title, intro, email, password, url, outro):
    btn = (f'<p style="margin:24px 0"><a href="{escape(url)}" style="background:#8a1c1c;color:#fff;'
           f'padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:bold">Ouvrir Mes collections</a></p>'
           if url else "")
    return f"""<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:auto;color:#1f1a17;line-height:1.5">
<h2 style="margin-bottom:4px">🗂️ {escape(title)}</h2>
<p>{intro}</p>{btn}
<table style="background:#f6f2ec;border-radius:6px;padding:12px 16px;margin:8px 0">
<tr><td style="padding:4px 12px 4px 0;color:#6b625b">Adresse</td><td>{escape(url) if url else "(demandez-la à l'administrateur)"}</td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#6b625b">E-mail</td><td><b>{escape(email)}</b></td></tr>
<tr><td style="padding:4px 12px 4px 0;color:#6b625b">Mot de passe provisoire</td><td><b style="font-family:monospace;font-size:15px">{escape(password)}</b></td></tr>
</table>
<p>{outro}</p>
<p style="color:#6b625b;font-size:12px">Message envoyé automatiquement par l'application Mes collections.</p></div>"""


def send_invitation(email, password, inviter=""):
    url = app_url()
    who = f"{inviter} vous invite" if inviter else "Vous êtes invité(e)"
    intro = (f"{escape(who)} à utiliser <b>Mes collections</b>, une application pour cataloguer vos disques "
             "78 tours, CD et livres (photo → fiche automatique, catalogue PDF…). Vos collections ne sont visibles que par vous.")
    outro = "À la première connexion, vous choisirez votre propre mot de passe."
    text = (f"{who} à utiliser Mes collections (catalogue de disques 78 tours, CD et livres).\n\n"
            f"Adresse : {url or '(demandez-la à l’administrateur)'}\nE-mail : {email}\n"
            f"Mot de passe provisoire : {password}\n\n{outro}\n")
    send(email, "Invitation à Mes collections", text, _html("Invitation à Mes collections", intro, email, password, url, outro))


def send_new_password(email, password, reason="reset"):
    url = app_url()
    intro = ("Un nouveau mot de passe provisoire a été créé pour votre compte <b>Mes collections</b>"
             + (" à votre demande (« Mot de passe oublié »)." if reason == "forgot" else " par l'administrateur."))
    outro = ("Vous devrez en choisir un nouveau à la connexion. Si vous n'êtes pas à l'origine de cette demande, "
             "connectez-vous avec ce mot de passe puis changez-le.")
    text = (f"Nouveau mot de passe provisoire pour Mes collections.\n\nAdresse : {url}\nE-mail : {email}\n"
            f"Mot de passe provisoire : {password}\n\n{outro}\n")
    send(email, "Votre nouveau mot de passe — Mes collections", text,
         _html("Nouveau mot de passe", intro, email, password, url, outro))
