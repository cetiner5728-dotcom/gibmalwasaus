# Floot-Batch-Implementierungsplan

## Batch A – Datenfundament
- Provider-Secrets zentral serverseitig konfigurieren: SPORTAPI_KEY, API_FOOTBALL_KEY, FOOTBALL_DATA_KEY, PITCHAPI_KEY, OPENFOOT_KEY, PUNTERSEDGE_KEY. Namen an tatsächliche Floot-Konventionen anpassen.
- Einheitliches Adapter-Interface: `fetchFixtures`, `fetchLive`, `fetchMatchDetails`, `fetchOdds`, `healthCheck`.
- Raw-Archive, Normalizer, Provider-Status und Quellenattribution.
- Kanonische Team-/Wettbewerbs-/Match-IDs plus Crosswalk-Tabellen.
- Dedupe- und Konfliktregeln implementieren.

## Batch B – Live-Center und Logos
- Live-Center aus SportAPI.ai plus PitchAPI/SportScore Cross-check.
- Live-Status, Minute, HT/FT, Tore, Karten, Wechsel, Schüsse/Ecken/Statistiken nur bei vorhandenen Datenfeldern anzeigen.
- Teamlogo aus Team-Stammdatensatz anhand stabiler Provider-Team-ID laden; Fallback auf Initialen.
- Stale/Conflict-Badges und `last_updated` je Quelle.

## Batch C – Quoten- und Marktmodul
- MoviOdds-Bet365-Quotes zuerst integrieren.
- PuntersEdge nach Prüfung der konkreten Buchmacher-/Marktabdeckung integrieren.
- TipsAudit als Fair-Odds-/Margin-Benchmark separat halten.
- Quote-Snapshots append-only speichern; Opening/Current/Closing nur bei belegter Definition.
- Bet%/Money% bleiben leer, solange keine echte Quelle existiert.

## Batch D – Modelle und Qualität
- Pre-match 1X2, Totals, BTTS, Team-Totals und Halbzeitmärkte nur mit ausreichenden Trainingsdaten.
- Live-Modelle nur mit zeitlich synchronisierten Live-Features.
- Chronologisches Walk-forward, Brier, LogLoss, Calibration, Sample Size, ROI und CLV getrennt je Markt/Liga.
- Keine Modellfreigabe auf Basis kleiner oder zeitlich vermischter Stichproben.

## Batch E – Bedienoberfläche
- WORLDWIDE BETTING RADAR Dashboard mit Live-Center, Matchdetails, Quotenvergleich, Prognose-Radar, Team-/Ligaansichten.
- Teamlogos in Live-Spielen, anstehenden Spielen, Ergebnissen, Tabellen und Teamprofilen.
- Filter nach Sport, Liga, Tag, Live/Upcoming/Finished und Markt.
- Mobile-first Layout.

## Ausführungsregel
Die fünf Batches in einer abgestimmten Floot-Arbeitsphase umsetzen. Erst nach Batch A die Adapter testen; danach B/C; Modell- und Dashboard-Freigabe erst nach QA. Keine unnötigen separaten Floot-Besuche. Keine Secrets in Code committen.