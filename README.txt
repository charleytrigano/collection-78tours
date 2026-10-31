MES COLLECTIONS (78 tours · CDthèque · Bibliothèque) — DÉPLOIEMENT

1. SUPABASE
- Créez un projet sur https://supabase.com/dashboard
- Ouvrez SQL Editor, collez le contenu de supabase_schema.sql, cliquez Run.
- Dans Project Settings > API, copiez Project URL et la clé service_role (secret).

2. IA (lecture des étiquettes) — au moins une des deux
- GEMINI (recommandé, bien meilleur pour lire les étiquettes anciennes ; offre gratuite) :
  créez une clé sur https://aistudio.google.com/apikey
- GROQ : créez une clé sur https://console.groq.com/keys
- Si les deux clés sont présentes, un bouton permet de choisir l'IA à chaque analyse.
- Sans clé, l'application fonctionne quand même : la fiche se saisit à la main.

3. STREAMLIT CLOUD
- Allez sur https://share.streamlit.io, connectez GitHub et déployez ce dépôt, branche main, fichier app.py.
- Dans App settings > Secrets, ajoutez en remplaçant les valeurs :

[supabase]
url = "https://VOTRE-PROJET.supabase.co"
service_role_key = "VOTRE_CLE_SERVICE_ROLE"

[gemini]
api_key = "VOTRE_CLE_API_GEMINI"
# model = "gemini-3.8-flash"

[groq]
api_key = "VOTRE_CLE_API_GROQ"
# Facultatif (les lignes model) : changer de modèle si celui par défaut n'est plus disponible
# model = "qwen/qwen3.8-27b"

[app]
password = "UN_MOT_DE_PASSE_LONG_ET_UNIQUE"

- Enregistrez puis redémarrez l'application.

ORGANISATION
- app.py : connexion par mot de passe et menu à gauche (78 tours, CDthèque, Bibliothèque).
- page_78tours.py : les disques 78 tours. page_cd.py et page_livres.py : CDthèque et Bibliothèque,
  construites sur collection_generic.py ; common.py regroupe les outils partagés (IA, photos, export).

CDTHÈQUE
- Photo de la pochette et du dos, ou code-barres : l'IA lit le boîtier et MusicBrainz complète
  pistes, label, année, référence ; la pochette officielle est récupérée si vous n'avez pas de photo.
- Écoutes (liens YouTube, Spotify, Deezer ou fichiers audio), présentation de l'album par l'IA.

BIBLIOTHÈQUE
- Photo de la couverture et de la 4e de couverture, ou ISBN : Google Books et Open Library complètent
  éditeur, année, pages, résumé et couverture. Champs Lu ? / Prêté à / Emplacement.

UTILISATION (78 tours)
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
