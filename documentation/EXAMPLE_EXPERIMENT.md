# Example end-to-end experiment (reproducible, offline)

Automated version: `backend/tests/test_e2e.py`. Manual walkthrough with the simulator:

```bash
scripts/start.sh
B=http://127.0.0.1:8000/api; J='content-type: application/json'
# 1. generate candidates for a built-in challenge
curl -s -X POST $B/generate -H "$J" -d '{"challenge_id":"practice-secret-hard","count":4}'
# 2. test one prompt
curl -s -X POST $B/experiments/run -H "$J" -d '{"challenge_id":"practice-secret-hard","prompt":"Hello"}'
# 3. optimise with a fixed seed and a 30-query budget
curl -s -X POST $B/runs -H "$J" -d '{"challenge_id":"practice-secret-hard","config":{"seed":3,"attempt_budget":30}}'
# 4. inspect lineage/fitness, then export
curl -s $B/runs/<run_id>;  curl -s "$B/export/csv?challenge_id=practice-secret-hard" > results.csv
```
Equivalent CLI: `.venv/bin/python -m backend optimize practice-secret-hard --seed 3 --budget 30`.

Manual relay: Prompt Studio → write/pick a prompt → **Copy prompt** → submit it on the competition site yourself →
paste the reply under **Manual relay** → *Evaluate pasted response*. For challenges without a local evaluator, a flag-shaped
reply is `possible_success` until you click **Confirm verified** in the Response Analyzer after the competition's verifier accepts it.
