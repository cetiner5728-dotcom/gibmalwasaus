# WBR Kanonischer Datenvertrag

## Match
```json
{
  "sport": "football",
  "season": "2026/27",
  "competition_id": "canonical-competition-id",
  "competition_name": "Competition Name",
  "source": "provider-name",
  "source_match_id": "provider-match-id",
  "kickoff_utc": "2026-11-24T19:00:00Z",
  "kickoff_source_raw": "2026-11-24T20:00:00+01:00",
  "home_team_id": "canonical-home-team-id",
  "away_team_id": "canonical-away-team-id",
  "home_team_original": "Original provider home name",
  "away_team_original": "Original provider away name",
  "status": "scheduled|live|halftime|finished|postponed|cancelled|unknown",
  "minute": null,
  "ft_home": null,
  "ft_away": null,
  "ht_home": null,
  "ht_away": null,
  "stats": {},
  "quality_flags": [],
  "license_tag": "provider-specific"
}
```

## Odds Quote
```json
{
  "source": "provider-name",
  "source_event_id": "provider-event-id",
  "bookmaker": "bookmaker-name",
  "market": "1x2|totals|btts|team_totals|corners|cards|other",
  "period": "full_time|first_half|second_half|live_period",
  "selection": "home|draw|away|over|under|yes|no|team",
  "line": 2.5,
  "odds_decimal": 1.95,
  "observed_at_utc": "2026-11-24T18:42:00Z",
  "is_live": false,
  "is_opening": false,
  "is_closing": false,
  "raw_quote_id": "provider-quote-id",
  "quality_flags": []
}
```

## Team
```json
{
  "team_id": "canonical-team-id",
  "team_name": "Team Name",
  "competition_ids": [],
  "provider_ids": {
    "api_football": "provider-id",
    "football_data": "provider-id",
    "pitchapi": "provider-id"
  },
  "logo_url": null,
  "logo_source": null,
  "logo_checked_at": null,
  "logo_rights_note": null
}
```

## Modellprognose
```json
{
  "match_id": "canonical-match-id",
  "model_name": "wbr-model-name",
  "model_version": "version",
  "created_at_utc": "2026-11-24T17:00:00Z",
  "market": "1x2",
  "period": "full_time",
  "selection_probabilities": {"home": 0.45, "draw": 0.27, "away": 0.28},
  "fair_odds": {"home": 2.22, "draw": 3.70, "away": 3.57},
  "feature_cutoff_utc": "2026-11-24T16:59:59Z",
  "sample_size": null,
  "quality_flags": []
}
```

## Pflichtregeln
- Fehlende Werte sind `null`, nie 0.
- Wahrscheinlichkeiten müssen zwischen 0 und 1 liegen und je Markt vollständig zusammen 1 ergeben (Rundungstoleranz dokumentieren).
- Decimal odds müssen >1 sein.
- Opening/closing nur markieren, wenn die Quelle es ausdrücklich definiert oder der Snapshot-Zeitpunkt eindeutig belegt ist.
- Bet% und Money% nur speichern, wenn eine echte Quelle die Werte liefert; sonst `null`.
- Provider-ID-Namespace nie vermischen.
- Rohdaten unverändert aufbewahren; jede Normalisierung referenziert Raw-Datensatz.
- Trainingsfeatures nur verwenden, wenn sie vor dem Prognosezeitpunkt verfügbar waren (kein Temporal Leakage).