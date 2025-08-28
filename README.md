# DB Designer (PIN-collab)

A tiny Flask app for collaboratively sketching database structures under a simple PIN stored in cookies. Not secure; intended for internal/temporary use.

## Features
- Join workspace by PIN (stored in cookie)
- Create/delete databases; add notes
- Create/delete tables; add notes
- Create/delete columns with properties: datatype, PK, nullable, default, note
- Create/delete links between tables or columns; add note
- Dark UI, JSON persistence per PIN in `.pin_data/`

## Quickstart

1. Create and activate a Python 3.11+ venv (recommended).
2. Install dependencies.
3. Run the app.

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Notes
- Data stored per PIN in `.pin_data/<PIN>.json` in the app folder
- This is not meant for production or sensitive data
- Deleting tables/columns also cleans up links that reference them

## Tests
Run a smoke test suite with pytest:

```powershell
.\.venv\Scripts\Activate.ps1
pytest -q
```
