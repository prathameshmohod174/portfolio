# Local Ollama iterative visual loop

Run from Windows PowerShell in the repository root:

powershell -ExecutionPolicy Bypass -File .\scripts\setup-local-ai-review.ps1

Then run:

.\scripts\run-local-ai-review.ps1

The loop:
- requires a clean Git worktree;
- starts from origin/main on a separate AI branch;
- captures desktop/mobile screenshots with existing Playwright tests;
- uses local Ollama vision inference to propose one small CSS-only patch at a time;
- reruns Playwright and asks the model to score the result;
- accepts a patch only when the estimated score improves by at least 0.2;
- stops at 8.5/10, after 10 iterations, or after 3 consecutive non-improving attempts;
- pushes accepted changes only after validation and creates a draft PR if GitHub CLI is installed and authenticated;
- never merges automatically.

The score is a heuristic from the local model, not an objective guarantee of design quality. This CSS-only first version cannot retrieve real Instagram/YouTube assets or rewrite project content. Those should be handled by a separate asset-ingestion workflow. The laptop must be awake, signed in, running Ollama, and connected to the internet for Git operations.
