# Kolejny GPX

Prywatna aplikacja Streamlit do zarzadzania trasami `.gpx`, kalendarzem terminow, historia uzyc oraz grupami tempowymi i pacers.

## Storage

Aplikacja obsluguje dwa tryby zapisu:

- `Supabase` jako docelowy, trwaly storage do wersji online
- `lokalny fallback` do pracy deweloperskiej

## Uruchomienie lokalne

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```
