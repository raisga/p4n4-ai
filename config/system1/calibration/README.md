# System 1 site calibration

Put a site's temperature file here, for example `site.json`:

```json
{"choice:3-5": 1.4, "choice:6-10": 1.6}
```

Keys are laya's buckets (`choice:2`, `choice:3-5`, `choice:6-10`, `choice:11+`) and values lie
in [0.5, 5]. Set `SYSTEM1_CALIBRATION=site.json` in `.env` and restart `system1`; a bad file
stops it at start-up. `p4n4 ai system1 eval --fit-calibration --save-calibration` fits and
writes it. A calibration changes every set's confidences, so evaluate every set again and
bump its version (system1.md §10.3).
