# WBR Team Logos – Integration Plan

## Zielbild
Teamwappen wie in professionellen Live-Score-Apps neben Heim- und Auswärtsteam, in Spielkarten, Tabellen, Teamprofilen und Matchdetails anzeigen.

## Verlässliche Zuordnung
- Primärschlüssel ist eine stabile Provider-Team-ID, nicht der sichtbare Teamname.
- Für jeden WBR-Teamdatensatz speichern: provider, provider_team_id, team_name_canonical, logo_url, logo_source, logo_checked_at, logo_rights_note.
- Provider-IDs bleiben getrennt (API-Football-ID ist nicht gleich football-data.org-ID).
- Namen-Aliase dienen nur zum Finden möglicher Matches; mehrdeutige Namen niemals automatisch zuordnen.
- Fehlende Wappen zeigen einen neutralen Initialen-Kreis, niemals ein falsches Logo.

## Bereits vorhandene Kandidaten
1. API-Football / API-Sports: Teams-Endpunkt liefert Team-ID und Logo; dokumentierte Medien-URL https://media.api-sports.io/football/teams/{team_id}.png. Die Dokumentation empfiehlt Logos zu speichern/cachen; Logos sind nicht Teil des normalen Tageskontingents, unterliegen aber Rate-Limits. Drittanbieterrechte bleiben zu beachten.
2. football-data.org: Teamobjekt enthält crest als Bild-URL. Gut als zweite Zuordnungsquelle für abgedeckte Wettbewerbe.
3. TipsAudit: Predictions-Endpunkt ist für 1X2-Fair-Odds nützlich; aus dem aktuell geprüften Payload allein ergibt sich keine belastbare Team-ID-/Logo-Zuordnung. Daher nicht als Logoquelle verwenden.

## Darstellung
- Kleine runde/contain Logos (ca. 28–36 px) neben Teamnamen.
- Auf Matchkarten beide Logos links/rechts vom Spielpaar; Tabellen kompakt.
- object-fit: contain, neutraler Hintergrund, Fallback bei HTTP-Fehlern.
- Logos niemals verzerren, umfärben oder als eigenes WBR-Branding ausgeben.

## Rechte und Caching
Provider-Logo-URLs sind keine automatische kommerzielle Lizenz. Vor öffentlicher/kommerzieller Veröffentlichung Nutzungsbedingungen und Rechte der jeweiligen Clubs/Ligen prüfen. Nur für Identifikation im Kontext der jeweiligen Begegnung verwenden. Keine Sammlung/Weiterveräußerung als Logo-Datenbank.

## Implementierungsreihenfolge
1. API-Football Team-IDs aus bereits geladenen Fixtures/Teams übernehmen (keine zusätzlichen teuren Polling-Aufrufe).
2. football-data.org crest als ergänzende Quelle für dessen eigene Team-IDs nutzen.
3. Team-Alias-/ID-Mapping einmalig pflegen und mehrdeutige Zuordnungen manuell prüfen.
4. Logo-URLs im WBR-Teamstamm cachen und auf Live-, Upcoming-, Result- und Standings-Karten anzeigen.
5. Metriken: Anteil der Teams mit validem Logo, fehlende Bilder, fehlerhafte Zuordnungen.

## Wichtiger aktueller Stand
TipsAudit Collector enthält derzeit keine Teamlogos. Logos gehören in den eigentlichen WBR-Match-/Team-Datenlayer; eine Zuordnung allein anhand von TipsAudit-Teamnamen wäre nicht zuverlässig.
