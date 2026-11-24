# WORLDWIDE BETTING RADAR – Floot-Übergabepaket

Stand: 24.11.2026

## Zweck
Dieses Verzeichnis ist die zentrale technische Übergabe für den späteren gebündelten Einbau in Floot. Es enthält Datenverträge, Quellenstatus, Integrationsreihenfolge und Abnahmekriterien. Es ist noch kein produktiver Floot-Import.

## Grundregeln
- Saisonfilter strikt: Fußball 2026/27; andere Sportarten nur Kalenderjahr 2026, sofern der Wettbewerb kalenderjährig geführt wird.
- Keine älteren Spielzeiten in den aktuellen Trainingsdatensatz mischen.
- Keine erfundenen Quoten, Bet%-/Money%-Werte, Aufstellungen, xG-Werte oder Prognosegüten.
- Rohdaten unverändert und append-only archivieren; Normalisierung separat.
- Zeitstempel immer mit UTC-Offset speichern; Originalzeit und Zeitzonenannahme erhalten.
- Provider-Team-IDs getrennt halten; Namen allein sind kein sicherer Join-Key.
- API-Keys nur in Floot Secrets/Environment Variables, niemals im Frontend, in GitHub-Dateien oder in Chatnachrichten.
- Kein kostenpflichtiger Tarif, Hosting, Datenbank, Deployment oder Veröffentlichung ohne ausdrückliche Freigabe.

## Paketinhalt
- `01_ARCHITECTURE.md` – Zielarchitektur und Module
- `02_DATA_CONTRACT.md` – kanonisches Match-/Odds-/Team-Schema
- `03_SOURCE_REGISTER.csv` – Quellenstatus, Nutzen und Grenzen
- `04_FLOOT_BATCH_PLAN.md` – gebündelte Implementierungsreihenfolge
- `05_QA_ACCEPTANCE.md` – Tests und Abnahmekriterien
- `06_TEAM_LOGOS.md` – Team-ID- und Logo-Integration

## Bereits außerhalb Floot vorhanden
- Mobiler TipsAudit Collector: `../tipsaudit/index.html`
- GitHub Actions Collector: `../.github/workflows/wbr-tipsaudit.yml`
- Collector-Skript: `../tools/tipsaudit_collect.py`
- Logo-Plan: `../tipsaudit/TEAM_LOGOS_PLAN.md`

## Noch nicht erledigt
- GitHub Actions Workflow-Lauf und Snapshot-Archivierung müssen verifiziert werden.
- Der Collector im Android-Browser wurde vom Nutzer erfolgreich geöffnet; ein Abruf wurde lokal gespeichert.
- Provider-Keys PitchAPI, OpenFoot und PuntersEdge sind erstellt, aber noch nicht in Floot verbunden.
- Noch keine vollständige aktuelle Saison-Datenlieferung aller 75 Open-Matchday-Wettbewerbe heruntergeladen.
- Noch kein produktiver Floot-Import, keine Live-Quotenabdeckung aller Buchmacher bestätigt.
- Noch keine Teamlogo-Abdeckung für alle WBR-Wettbewerbe gemessen.

## Release-Regel
Floot-Einbau erst starten, wenn Datenverträge, Quellenlimits, Schlüsselverwaltung und Testfälle in einem gemeinsamen Batch umgesetzt werden können. Vorher kein ständiges Ein- und Ausloggen in Floot.