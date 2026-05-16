# PHP Code Generator Tools - GenCode AI

A Django-based AI coding assistant for generating company-pattern PHP forms from uploaded codebases, coding standards, and natural language prompts.

## Features

- User registration, login, and dashboard workflow
- Project management UI for organizing generated work
- Codebase upload and indexing workflow
- Coding standards authoring and upload UI
- AI-assisted PHP form generation UI
- Safe empty-state onboarding when API key, codebase, or standards are missing
- Runtime storage isolation so private uploads and vector data stay out of Git

## Tech Stack

- Django
- Django REST Framework
- LangChain / LangGraph
- OpenAI API
- ChromaDB
- HTML, CSS, JavaScript

## Screenshots

- Add screenshots here after preparing your public demo environment.

## Local Setup

### Windows

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Linux / Mac

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Environment Variables

Copy `.env.example` to `.env` and update only the values you need:

```env
SECRET_KEY=change-me-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

DATABASE_URL=sqlite:///db.sqlite3

CHROMA_PERSIST_DIRECTORY=./runtime/chroma
CODEBASE_STORAGE_DIR=./runtime/company_codebases
MEDIA_ROOT=./media
STATIC_ROOT=./staticfiles

EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
```

## Database Setup

- The default configuration uses SQLite via `DATABASE_URL=sqlite:///db.sqlite3`.
- For a fresh local setup, run `python manage.py migrate`.
- Create an admin account with `python manage.py createsuperuser`.

## Running the App

```bash
python manage.py migrate
python manage.py runserver
```

Then open `http://127.0.0.1:8000/`.

## Uploading Your Own Codebase

1. Register or log in.
2. Open the Codebase page.
3. Upload your own PHP project ZIP.
4. Wait for indexing to finish before using company-pattern generation.

If no OpenAI API key is configured, the app stores the uploaded ZIP safely but skips indexing until a key is added.

## Configuring OpenAI API Key

- Set `OPENAI_API_KEY` in `.env` or your deployment environment.
- The Settings page shows only whether the key is configured.
- The app never displays the raw secret value in the UI.

## Deployment Notes for PythonAnywhere

### Deployment Checklist

1. Clone the repo.
2. Create a virtualenv.
3. `pip install -r requirements.txt`
4. Create `.env` from `.env.example`
5. Add `SECRET_KEY` and `OPENAI_API_KEY` in `.env` or environment settings
6. Run migrations
7. Create a superuser
8. Configure the WSGI file
9. Configure static files
10. Reload the web app

### Suggested PythonAnywhere Flow

```bash
git clone git@github.com:AbdulSattar5/PHP_CODE_GENERATORS_TOOLS_.git
cd PHP_CODE_GENERATORS_TOOLS_
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

Set your WSGI file to point at the project and reload the PythonAnywhere web app after any config change.

## Security Notes

This repository intentionally does not include:

- API keys
- uploaded company codebases
- vector databases
- embeddings
- generated private outputs
- private database records

Secrets must be supplied through `.env` or platform environment variables only.

## What Is Intentionally Not Included

- Real company PHP source code
- Uploaded ZIP archives from private clients or internal systems
- Extracted runtime codebases
- ChromaDB persistence data
- Embedding caches and chunk indexes
- Generated PHP output from private codebases
- Private SQLite database records
- Private logs and runtime temp files

## License

- Add your preferred license here before publishing publicly.
