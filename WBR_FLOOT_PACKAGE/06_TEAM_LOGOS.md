# Teamlogo-Integration

## Ziel
Echte Vereinswappen wie in professionellen Livescore-Anwendungen neben Teamnamen anzeigen: Live, Upcoming, Finished, Tabellen, Matchdetails und Teamprofile.

## Zuordnungsregeln
- Kanonische WBR-Team-ID als interne Identität.
- Provider-Team-IDs in getrennten Namespaces speichern; niemals IDs unterschiedlicher Provider gleichsetzen.
- Logo-Zuordnung primär über stabile Provider-Team-ID, nicht nur über den sichtbaren Namen.
- Namen-Aliase helfen bei der Kandidatensuche; mehrdeutige Matches benötigen manuelle Bestätigung.
- Fehlt ein gültiges Logo, Initialen-Kreis als Fallback verwenden. Nie ein geratenes Wappen anzeigen.

## Quellen
- API-Football/API-Sports: Teamdatensätze enthalten ID und Logo-URL; Team-Endpunkt und Medien-URL nur mit vorhandener Provider-ID verwenden.
- football-data.org: Teamobjekte können `crest` enthalten; nur für deren eigene Team-IDs verwenden.
- TipsAudit: im geprüften Predictions-Payload keine belastbare Team-ID-/Logo-Verknüpfung; nicht als Logoquelle nutzen.

## Team-Stammdatenfelder
`team_id`, `team_name`, `provider_ids`, `logo_url`, `logo_source`, `logo_checked_at`, `logo_rights_note`, `logo_status`.

## UI-Regeln
- Bildgröße etwa 28–36 px, `object-fit: contain`, nicht verzerren oder umfärben.
- Auf Matchkarten Heim- und Auswärtslogo mit Teamnamen und Ergebnis/Spielstand zeigen.
- In Tabellen kompakte Logos vor Teamnamen.
- Bei Ladefehlern sofort Fallback auf Initialen; Layout darf nicht springen.

## Rechte und Betrieb
- Provider-Logo-URLs bedeuten nicht automatisch eine kommerzielle Lizenz.
- Vor öffentlicher oder kommerzieller Nutzung Nutzungsbedingungen und Club-/Liga-Rechte prüfen.
- Logos nur im Identifikationskontext des jeweiligen Teams nutzen; keine Logo-Datenbank weiterverkaufen.
- Logos cachen und nicht bei jedem Live-Poll erneut abfragen.

## QA
- Stichprobe aus allen Wettbewerben prüfen.
- Fehlzuordnungen, fehlende Logos, defekte URLs und Abdeckungsquote protokollieren.
- Kein Go-live bei ungeklärter Teamzuordnung oder unklarer Nutzungsberechtigung.
