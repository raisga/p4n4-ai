# System 1 draft sets (not shipped)

S3 drafted four question sets. None of them ships: on the base checkpoints, none passes its gates
in a way that holds on held-out examples. S4 fine-tuned `multilingual` on a generic synthetic
corpus (`../train/`) and they got much closer, but still not there (p4n4-docs
`decisions/system1.md` §16 and §17). The service never loads this folder, and the image doesn't
copy it.

| Set | Use case | Examples | Base `multilingual` | Fine-tuned `multilingual` (S4) |
|-----|----------|---------:|---------------------|--------------------------------|
| `log-triage` | U5: one log line → network, auth, disk, memory, crash, config | 57 | At 0.95: coverage 0.29, confident-wrong 0.018. Held out in 0 of 3 splits | At 0.97: coverage 0.73, accuracy 0.97, confident-wrong 0.018. Held out in 1 of 3 |
| `device-class` | U4: a new device's readings → device type | 61 | At 0.87: coverage 0.29, confident-wrong 0.016. Held out in 0 of 3 | Coverage 0.98, accuracy 0.98, confident-wrong 0.016 at any threshold. Held out in 1 of 3 |
| `system2-router` | U3: none, Ollama or a Letta agent | 52 | Confident-wrong ≤ 0.03 only from 0.94, at coverage 0.07 | At 0.85: coverage 0.95, accuracy 0.98, confident-wrong 0.019. Held out in 1 of 3 |
| `anomaly-screen` | U6: rank windows by P(`explain`) | 52 | AUC 0.67 (gate 0.8) | AUC 0.83 |

- **Why they still don't ship.** On the whole file the fine-tuned checkpoint passes every gate
  of the three thresholded sets. But a third of a file is about 18 examples, and one confident
  miss there is already a confident-wrong rate over 0.03. In 2 of 3 splits, the third the
  threshold wasn't fitted on had that miss. The anomaly file passes its gate, on 52 windows that
  the corpus's author also wrote. The next step is more examples, best a site's own, not more
  training.
- **The data is generic and synthetic.** The labels are this repository's. Some are debatable,
  for example an `OOMKilled` exit labelled `memory` rather than `crash`.
- **`log-triage` assumes a rule first.** The workflow would pass a line to System 1 only when it
  looks like an error, so routine lines never reach it. The file holds what such a filter lets
  through.
- **The training corpus never saw these files.** `../train/corpus.py` drops any generated example
  that shares 70 % of its words with one of them.
- **To ship one of these:** reach its gates held out, on a site's own examples or a larger file,
  with the checkpoint the service runs. Then set its thresholds, bump its version, and move it to
  `config/system1/questions/`.
