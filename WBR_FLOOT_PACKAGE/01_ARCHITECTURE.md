# WBR Zielarchitektur

## Schichten
1. **Provider Adapter** – je Quelle ein Adapter mit eigener Authentifizierung, Rate-Limit, Retry und Status.
2. **Raw Archive** – unveränderte Antworten mit Provider, Endpoint, Abrufzeit, HTTP-Status und Lizenzkennzeichnung.
3. **Normalizer** – übersetzt Provider-Felder in den kanonischen WBR-Vertrag.
4. **Entity Resolver** – ordnet Wettbewerbe, Teams und Spiele über Provider-IDs und geprüfte Crosswalks zu.
5. **Quality Gate** – prüft Zeit, Saison, Dubletten, Scores, Status, Plausibilität und Konflikte.
6. **WBR Store** – normalisierte Spiele, Teamstamm, Quoten-Snapshots, Modellprognosen und Ergebnis-Historie.
7. **Model & Analytics** – Pre-match, Halbzeit, Live-Modelle, Kalibrierung, EV, CLV und Backtesting.
8. **Presentation** – Live-Center, Matchkarten, Tabellen, Teamlogos, Quotenvergleich und Radar-Dashboard.

## Provider-Rollen
- Live-Ergebnisse/Events: SportAPI.ai als bestehende Quelle; PitchAPI und SportScore als unabhängige Gegenprüfung; OpenFoot als zusätzlicher Fixture-/Statistik-Adapter.
- Statistiken/xG: PitchAPI und OpenFoot nur dort, wo Wettbewerb und Tarif die Felder tatsächlich liefern; API-Football als bestehende Ergänzung.
- Fixtures/Ergebnisse: football-data.org, OpenLigaDB für unterstützte Ligen, Open-Matchday/Football-Data nur nach Lizenzprüfung.
- Quoten: MoviOdds (Bet365-Feed, bereits getestet), PuntersEdge, TipsAudit als Markt-/Fair-Odds-Benchmark, weitere Aggregatoren erst nach konkreter Coverage- und Kostenprüfung.
- TipsAudit ist kein Liveticker und kein vollständiger Multi-Markt-Oddsfeed.

## Live-Aktualisierung
- Nicht alle Provider im gleichen Takt pollen.
- Live-Feeds gemäß dokumentiertem Limit und tatsächlicher Nutzungsquote pollen; bei PitchAPI Live-Abfragen nicht schneller als dokumentierte 10 Sekunden.
- Exponential backoff bei 429/5xx; keine Endlosschleifen.
- Pro Quelle `last_success_at`, `last_error_at`, `latency_ms`, `remaining_quota` (falls geliefert), `stale_after_seconds` führen.
- Bei Ausfall nicht stillschweigend alte Werte als live anzeigen: deutlich `STALE` kennzeichnen.

## Konfliktauflösung
- Mehrere Quellen dürfen nicht blind zusammengeführt werden.
- Scores: Primärquelle plus unabhängige Bestätigung; Widerspruch als `CONFLICT` markieren.
- Status und Spielminute mit `source_updated_at` vergleichen.
- xG und Schussdaten nicht über Anbieter hinweg mitteln, solange Definitionen nicht harmonisiert sind.
- Odds: jede Quote bleibt mit Buchmacher, Markt, Linie, Zeitraum und Beobachtungszeitpunkt separat.

## Sicherheits- und Betriebsregeln
- Secrets ausschließlich serverseitig.
- Frontend bekommt nur bereinigte WBR-Daten, niemals Provider-Keys.
- Keine Browser-CORS-Workarounds mit geheimen Schlüsseln.
- Keine Scraping- oder Zugriffssperren-Umgehung.
- Provider-Lizenzen und Attributionspflichten pro Datensatz/Ansicht beachten.