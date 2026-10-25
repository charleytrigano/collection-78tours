COLLECTION 78 TOURS — DÉPLOIEMENT

1. SUPABASE
- Créez un projet sur https://supabase.com/dashboard
- Ouvrez SQL Editor, collez le contenu de supabase_schema.sql, cliquez Run.
- Dans Project Settings > API, copiez Project URL et la clé service_role (secret).

2. GROQ (identification des étiquettes par IA)
- Créez une clé API sur https://console.groq.com/keys
- Sans clé, l'application fonctionne quand même : la fiche se saisit à la main.

3. STREAMLIT CLOUD
- Allez sur https://share.streamlit.io, connectez GitHub et déployez ce dépôt, branche main, fichier app.py.
- Dans App settings > Secrets, ajoutez en remplaçant les valeurs :

[supabase]
url = "https://VOTRE-PROJET.supabase.co"
service_role_key = "VOTRE_CLE_SERVICE_ROLE"

[groq]
api_key = "VOTRE_CLE_API_GROQ"
# Facultatif : autre modèle vision Groq si celui par défaut n'est plus disponible
# model = "qwen/qwen3.8-27b"

[app]
password = "UN_MOT_DE_PASSE_LONG_ET_UNIQUE"

- Enregistrez puis redémarrez l'application.

UTILISATION
- Ajouter : photographiez les faces A et B (pochette facultative), cliquez « Analyser », relisez, enregistrez.
  Le formulaire se vide tout seul pour enchaîner le disque suivant. Un doublon de référence est signalé.
- Catalogue : recherche, filtres (label, état, pochette), tri ; cliquez une ligne pour voir la fiche,
  la modifier (y compris remplacer une photo) ou la supprimer.
- Récapitulatif : valeur estimée, graphiques par état et par décennie, disques les plus estimés,
  fiches incomplètes.
- Exporter : Excel (.xlsx) ou CSV (séparateur point-virgule, compatible Excel français).

SÉCURITÉ
- Passez le dépôt GitHub en Private dans Settings > General > Danger Zone.
- Ne mettez jamais les clés dans GitHub.
- L'application a un écran simple par mot de passe. Ne partagez ni ce mot de passe ni les clés secrètes.
- Vérifiez les informations et estimations IA avant de les valider.
