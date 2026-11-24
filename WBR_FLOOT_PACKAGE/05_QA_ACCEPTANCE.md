# WBR QA- und Abnahmekriterien

## Quellen
- Jeder Provider zeigt HTTP-Status, Abrufzeit, Latenz, letzte erfolgreiche Antwort und bekannte Quoten-/Rate-Limit-Informationen.
- Fehlende oder ausgefallene Quelle erzeugt einen sichtbaren Status, nicht stillen Fallback auf alte Live-Daten.
- Live-Daten älter als konfigurierte Schwelle werden als STALE markiert.

## Datenqualität
- Saisonfilter: Fußball 2026/27; keine älteren Spielzeiten im aktuellen Trainingssatz.
- Keine Duplikate nach canonical match ID; ungeklärte Cross-Provider-Zuordnungen bleiben getrennt.
- Score-/Statuskonflikte werden markiert und nicht stillschweigend überschrieben.
- HT, FT, Minute, xG, Schüsse, Karten und Ecken werden nur angezeigt, wenn geliefert; fehlend = null.
- Kickoff-Zeiten mit korrektem UTC-Offset; Sommerzeit-Fehler sichtbar flaggen.

## Quoten
- Jede Quote mit Buchmacher, Markt, Linie, Periode, Zeitstempel und Live/Pre-match-Kennzeichen.
- Opening/Closing nur mit belegter Definition.
- Margen korrekt aus einer vollständigen Marktquote berechnet; keine falschen Vergleiche bei unterschiedlichen Märkten.
- Bet%/Money% nur bei direkter Quelle; sonst „nicht verfügbar“.

## Teamlogos
- Teamzuordnung über Provider-Team-ID, nicht nur Namen.
- Keine falschen Logos bei Namensgleichheit oder Alias-Konflikten.
- Fallback mit Initialen bei fehlendem Logo.
- Logo-URL und Herkunft dokumentiert; Rechte-/Attributionsprüfung vor öffentlicher kommerzieller Nutzung.

## Modellgüte
- Brier, LogLoss und Kalibrierung mit Stichprobengröße und Zeitraum anzeigen.
- Chronologischer Walk-forward ohne Leakage.
- CLV nur bei gespeicherter Empfehlungsquote und belegter Closing-Quote.
- ROI/Hitrate nicht ohne abgeschlossene, nachvollziehbare Ergebnisdaten veröffentlichen.

## Go-live Gate
Kein Go-live, solange kritische Tests für Secrets, Datenzuordnung, Zeitstempel, Dubletten, Stale-Markierung und Quellenlizenzen fehlschlagen.