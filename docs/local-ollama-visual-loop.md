# Local Ollama iterative visual loop

Run from Windows PowerShell in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-local-ai-review.ps1
.\scripts\run-local-ai-review.ps1
```

The loop:
- requires a clean Git worktree;
- starts from `origin/main` on a separate AI branch;
- captures desktop/mobile screenshots with existing Playwright tests;
- uses local Ollama vision inference to score six dimensions: imagery, project differentiation, completeness, mobile composition, legibility, and cinematic identity;
- runs a deterministic HTML audit for actual media in project cards, generic project titles, external source links, and visible role/category labels;
- caps the evaluated score when the site lacks real project media or has multiple generic titles, so a high aesthetic score cannot mask portfolio-readiness gaps;
- proposes one small CSS-only patch at a time, then reruns Playwright and reevaluates the screenshots;
- accepts a patch only when the evaluated score improves by at least 0.2 and browser tests pass;
- considers the 8.5/10 target reached only when the evaluated score meets the target **and** all deterministic readiness gates pass;
- stops at the target, after 10 iterations, after 3 consecutive non-improving attempts, or when the model has no useful CSS-only improvement;
- writes `local-ai-review-report.json` with rubric scores, readiness blockers, and iteration history;
- pushes accepted changes only after validation and creates a draft PR if GitHub CLI is installed and authenticated;
- never merges automatically.

The local model's rubric remains heuristic, not an objective guarantee. The deterministic audit verifies only the HTML patterns listed above; it does not verify the visual or factual quality of linked external media. CSS-only iteration cannot fix missing images, vague project names, or inaccurate credits. Those require an asset/content pass, and the report will name these blockers instead of falsely declaring the target reached. The laptop must be awake, signed in, running Ollama, and connected to the internet for Git operations.
