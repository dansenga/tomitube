# Tomitube

Tomitube est une application Streamlit moderne pour telecharger des videos YouTube (MP4 avec audio) ou extraire l'audio (MP3).

## Fonctionnalites

- Analyse automatique de l'URL YouTube
- Affichage du titre, de la miniature et de la duree
- Selection de qualite video parmi 360p, 720p, 1080p (si disponibles)
- Telechargement video MP4 avec audio garanti (fusion video + audio)
- Telechargement audio uniquement en MP3
- Barre de progression en temps reel pendant le telechargement
- Gestion des erreurs: URL invalide, video indisponible, probleme reseau
- Historique de telechargement sur la session
- Preview video dans l'interface

## Prerequis

- Python 3.10+
- FFmpeg installe sur la machine (obligatoire pour fusionner video/audio et convertir en MP3)

### Installer FFmpeg

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

Verifier l'installation:

```bash
ffmpeg -version
```

## Installation

Depuis la racine du projet:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Lancer Tomitube en local

```bash
streamlit run Tomitube.py
```

Puis ouvrir l'URL locale affichee par Streamlit (en general http://localhost:8501).

## Deploiement (Streamlit Community Cloud)

1. Pousser le projet sur GitHub.
2. Dans Streamlit Cloud, creer une nouvelle app.
3. Selectionner le repo et la branche.
4. Definir le fichier principal: `Tomitube.py`.
5. Verifier que le fichier `requirements.txt` est a la racine.
6. Deployer.

## Notes techniques

- Les selections de format evitent les IDs fixes yt-dlp pour limiter les erreurs de format indisponible.
- Le mode video utilise un selecteur avec fallback pour garder le son.
- L'historique est stocke dans `st.session_state` (session courante uniquement).
