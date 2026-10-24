# Einrichtung und Betrieb

## Hintergrund

Die [Social-Login-App](https://apps.nextcloud.com/apps/sociallogin) aktualisiert Gruppen bei der Browser-Anmeldung. Dauerhaft angemeldete Mobil- und Desktop-Clients lösen dies häufig nicht aus. Dieses Skript gleicht die Gruppen deshalb unabhängig davon über die Nextcloud-Verwaltungsschnittstelle ab.

Die [ChurchTools-Anleitung zur OAuth-Anmeldung](https://churchtools.academy/de/help/system-einstellungen/oauth-login-systemeinstellungen/oauth-login-via-churchtools-bei-nextcloud) beschreibt die Grundkonfiguration. Eine alternative Anbindung ist die [ChurchTools-Integrations-App](https://apps.nextcloud.com/apps/churchtools_integration).

## Konfiguration

| Variable                                    | Bedeutung                                                                       |
| ------------------------------------------- | ------------------------------------------------------------------------------- |
| `CT_BASE_URL`, `CT_LOGIN_TOKEN`             | ChurchTools-Instanz und Login-Token                                             |
| `NC_BASE_URL`, `NC_USERNAME`, `NC_PASSWORD` | Nextcloud-Instanz und Administrationskonto                                      |
| `NC_GROUP_PREFIX`                           | Exaktes Präfix der durch Social Login verwalteten Gruppen, z. B. `ChurchTools-` |
| `NC_GROUPS_CLAIM`                           | `groups` für Gruppen oder `roles` für Gruppen und Rollen                        |
| `DRY_RUN`                                   | `true` für Vorschau, `false` für Änderungen; Standard: `true`                   |
| `REMOVE_EXTRA_GROUPS`                       | Veraltete Zuordnungen innerhalb des Präfixes entfernen; Standard: `true`        |
| `LOG_LEVEL`, `LOG_FORMAT`                   | Protokollstufe und Darstellung                                                  |
| `LOG_FILE`                                  | Optionaler Pfad für rotierende Dateiprotokolle                                  |

Weitere Beispiele stehen in [.env.example](../.env.example). Zugangsdaten ausschließlich lokal oder in der Server-Umgebungsverwaltung hinterlegen.

## Berechtigungen und Präfix

Der ChurchTools-Token benötigt Leserechte auf alle relevanten Personen und Gruppen. Eingeschränkte Rechte führen zu unvollständigen Ergebnissen. Hinweise zur [API-Authentifizierung](https://churchtools.academy/de/help/system-einstellungen/api/api-authentifizierung/) stehen in der ChurchTools-Dokumentation.

In Nextcloud ein eigenes lokales Administrationskonto verwenden und dessen reguläres Passwort setzen. App-Passwörter scheitern gegebenenfalls mit `403 Password confirmation is required`, da diese Verwaltungsaktionen eine Passwortbestätigung verlangen. Die vorhandene Nextcloud-Schutzfunktion muss für den Betrieb nicht global abgeschaltet werden.

Das Präfix muss exakt dem internen Namen der OAuth-Verbindung mit anschließendem Bindestrich entsprechen. Nur so findet das Skript die bestehenden Social-Login-Gruppen. Gruppen außerhalb des Präfixes, etwa `admin`, bleiben unberührt.

Im Modus `groups` heißt eine Gruppe beispielsweise `ChurchTools-Technik`; im Modus `roles` etwa `ChurchTools-Technik_Leitung`. Archivierte ChurchTools-Gruppen sind eingeschlossen: Archivieren allein entfernt die Zuordnung deshalb nicht.

Schlägt die Gruppenabfrage einer Person fehl oder liefert ungültige Daten, bleiben deren Nextcloud-Zuordnungen unverändert; eine Warnung und die Zahl übersprungener Personen werden protokolliert. Eine erfolgreich geladene leere Gruppenliste kann dagegen veraltete Zuordnungen entfernen.

## Aufrufe und Protokolle

```sh
python main.py --dry-run
python main.py --sync
python main.py --sync --no-remove-extra
python main.py --dry-run --claim roles --prefix ChurchTools-
python main.py --dry-run --log-level DEBUG --log-format detailed --log-file logs/sync.log
```

`--remove-extra` aktiviert das Entfernen veralteter Zuordnungen, `--no-remove-extra` schaltet es aus. `--claim` akzeptiert `groups` und `roles`. Protokollstufen: `DEBUG`, `INFO`, `WARNING`, `ERROR`; Formatvorlagen: `simple`, `detailed`, `compact`, `plain` oder ein eigenes Format. `python main.py --help` zeigt die vollständigen Optionen.

## Docker und Dokploy

In Dokploy eine Anwendung über die GitHub-Verbindung mit diesem Repository und dem [Dockerfile](../Dockerfile) einrichten. Die Umgebungsvariablen dort hinterlegen und deployen. Der Container wartet mit `tail -f /dev/null` auf geplante Aufrufe.

Ein Zeitplan führt `python main.py --sync` aus, beispielsweise alle fünf Minuten (`*/5 * * * *`) oder alle 30 Minuten (`*/30 * * * *`). Vorher denselben Aufruf mit `--dry-run` prüfen. Siehe [Dokploy-Zeitpläne](https://docs.dokploy.com/docs/core/schedule-jobs).

## Cron und Systemd

Alternativ in einer Crontab:

```cron
*/5 * * * * cd /opt/churchtools-nextcloud-sync && .venv/bin/python main.py --sync
```

Oder eine Unit `/etc/systemd/system/ct-nc-sync.service` anlegen. Das angegebene Betriebskonto muss auf Projekt und Konfiguration zugreifen können:

```ini
[Unit]
Description=ChurchTools-Gruppen mit Nextcloud abgleichen
After=network.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/opt/churchtools-nextcloud-sync
ExecStart=/opt/churchtools-nextcloud-sync/.venv/bin/python main.py --sync
```

Dazu `/etc/systemd/system/ct-nc-sync.timer`:

```ini
[Unit]
Description=Gruppenabgleich alle fünf Minuten

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
```

Anschließend `sudo systemctl daemon-reload` und `sudo systemctl enable --now ct-nc-sync.timer` ausführen. Ein Ausfall der Datenquellen muss über die Protokolle geprüft werden; die Vorschau ersetzt keine Prüfung der produktiven Berechtigungen.
