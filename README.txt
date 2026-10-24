COLLECTION 78 TOURS — DÉPLOIEMENT

1. SUPABASE
- Créez un projet sur https://supabase.com/dashboard
- Ouvrez SQL Editor, collez le contenu de supabase_schema.sql, cliquez Run.
- Dans Project Settings > API, copiez Project URL et la clé service_role (secret).

2. OPENAI
- Créez une clé API sur https://platform.openai.com/api-keys
- L'API est facturée séparément de l'abonnement ChatGPT.

3. STREAMLIT CLOUD
- Allez sur https://share.streamlit.io, connectez GitHub et déployez ce dépôt, branche main, fichier app.py.
- Dans App settings > Secrets, ajoutez en remplaçant les valeurs :

[supabase]
url = "https://VOTRE-PROJET.supabase.co"
service_role_key = "VOTRE_CLE_SERVICE_ROLE"

[openai]
api_key = "VOTRE_CLE_API_OPENAI"

[app]
password = "UN_MOT_DE_PASSE_LONG_ET_UNIQUE"

- Enregistrez puis redémarrez l'application.

SÉCURITÉ
- Passez le dépôt GitHub en Private dans Settings > General > Danger Zone.
- Ne mettez jamais les clés dans GitHub.
- L'application a un écran simple par mot de passe. Ne partagez ni ce mot de passe ni les clés secrètes.
- Vérifiez les informations et estimations IA avant de les valider.
