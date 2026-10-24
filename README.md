<div align="center">
  <img src=".github/assets/logo.png" alt="Christen am Güterplatz" width="112" height="112">
  <h1>ChurchTools–Nextcloud-Synchronisation</h1>
  <p>Gruppenmitgliedschaften unabhängig von der nächsten Browser-Anmeldung abgleichen.</p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white">
  <img alt="Nextcloud" src="https://img.shields.io/badge/Nextcloud-0082C9?logo=nextcloud&logoColor=white">
  <p><a href="https://www.christen-am-gueterplatz.de">Gemeindewebseite</a> · <a href="https://github.com/Christen-am-Gueterplatz">Unsere Projekte</a></p>
</div>

## Überblick

Synchronisiert ChurchTools-Gruppen und Rollen mit Nextcloud-Gruppen bei Nutzung der Social-Login-App. Dadurch erhalten auch Personen mit dauerhaft angemeldeter Mobil- oder Desktop-App ihre aktuellen Gruppenzuordnungen.

Fehlende Gruppen werden angelegt. Änderungen betreffen ausschließlich Gruppen mit dem konfigurierten Präfix. Fehlgeschlagene Mitgliedschaftsabfragen führen dazu, dass die betroffene Person für diesen Lauf übersprungen wird.

## Technik

Python, `nc-py-api` mit asynchronen Nextcloud-Aufrufen, ChurchTools-API und Docker. Der Container kann über Dokploy-Zeitpläne oder einen klassischen Server-Timer aufgerufen werden.

## Schnellstart

```sh
python -m venv .venv
```

Die virtuelle Umgebung aktivieren (`source .venv/bin/activate` unter Linux, `.\.venv\Scripts\Activate.ps1` unter Windows), dann:

```sh
pip install -r requirements.txt
```

[.env.example](.env.example) als `.env` kopieren, Verbindungen und Präfix eintragen und zunächst eine Vorschau ausführen:

```sh
python main.py --dry-run
```

Erst nach Prüfung mit `python main.py --sync` anwenden. `--sync --no-remove-extra` ergänzt ausschließlich fehlende Zuordnungen.

## Dokumentation

Die [Betriebsanleitung](docs/betrieb.md) beschreibt Berechtigungen, Präfixe, Rollen, Fehlerbehandlung, Protokolle sowie Docker, Dokploy, Cron und Systemd.

**Für Nextcloud wird das reguläre Passwort eines Administrationskontos benötigt:** App-Passwörter können bei diesen Verwaltungsaufrufen an der Passwortbestätigung scheitern. Das genaue Präfix und vollständige ChurchTools-Leserechte sind vor einem schreibenden Lauf zu prüfen.

## Lizenz

[MIT-Lizenz](LICENSE).
