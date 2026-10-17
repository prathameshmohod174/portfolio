import base64, json, os, re, subprocess, sys, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SHOTS = ROOT / "test-results" / "screenshots"
MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
API = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
TARGET = float(os.environ.get("VISUAL_TARGET", "8.5"))
MAX_ITERATIONS = min(10, max(1, int(os.environ.get("VISUAL_MAX_ITERATIONS", "10"))))
MIN_GAIN = float(os.environ.get("VISUAL_MIN_GAIN", "0.2"))

def run(args, check=True, capture=False):
    print("+", " ".join(str(x) for x in args), flush=True)
    return subprocess.run(args, cwd=ROOT, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None)

def screenshots():
    run(["npm", "run", "test:chromium"])
    paths = [SHOTS / "desktop.png", SHOTS / "mobile.png"]
    if not all(p.exists() for p in paths):
        raise RuntimeError("Playwright did not create both desktop and mobile screenshots.")
    return [base64.b64encode(p.read_bytes()).decode("ascii") for p in paths]

def model_json(prompt, images):
    payload = {"model": MODEL, "stream": False, "format": "json",
        "messages": [{"role": "user", "content": prompt, "images": images}],
        "options": {"temperature": 0.1, "num_predict": 1200}}
    req = urllib.request.Request(API, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Ollama returned an empty response.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama response was not valid JSON: " + content[:250]) from exc
    if not isinstance(data, dict):
        raise RuntimeError("Ollama response was not a JSON object.")
    return data

def css_now(html):
    match = re.search(r"<style[^>]*>(.*?)</style>", html, re.I | re.S)
    if not match:
        raise RuntimeError("Could not locate the stylesheet.")
    return match.group(1)

def valid_patch(patch):
    if not isinstance(patch, str) or not patch.strip() or len(patch) > 1800:
        return False
    if re.search(r"@|url\s*\(|expression\s*\(|javascript:|</?style|<script|</", patch, re.I):
        return False
    if patch.count("{") != patch.count("}") or patch.count("{") > 5:
        return False
    if re.search(r"(^|[,{])\s*(html|body|:root|\*)\s*(?=[,{])", patch, re.I):
        return False
    return True

def ask_for_proposal(html, images, current_score):
    prompt = (
        "You are a senior web designer improving the Random Hours cinematic creative portfolio. "
        "Review attached screenshots (desktop then mobile). The current estimated visual quality score is "
        + str(current_score) + "/10. Return ONLY JSON: {\"score\": number, \"changed\": boolean, "
        "\"summary\": string, \"css\": string}. Score current visual design from 1 to 10. "
        "If score is at least " + str(TARGET) + " or no meaningful improvement exists, changed=false and css=''. "
        "Otherwise propose one high-impact CSS-only improvement. At most 5 simple rules, under 1800 chars. "
        "No at-rules, url(), external assets, scripts, HTML, or selectors html/body/:root/*. "
        "Do not claim to fix missing images with CSS; do not change content or links. Prefer real usability, "
        "hierarchy, spacing and responsive composition over decorative effects. Current CSS follows:\n"
        + css_now(html)[:9000]
    )
    return model_json(prompt, images)

def score_current(html, images):
    prompt = (
        "Assess the current Random Hours portfolio design from the attached desktop and mobile screenshots. "
        "Return ONLY JSON {\"score\": number, \"summary\": string}. Score visual quality from 1 to 10, "
        "considering hierarchy, spacing, responsiveness, legibility, project presentation and cinematic identity. "
        "Do not reward visual effects just for existing. Do not assume images exist if they are placeholders. "
        "Be consistent and conservative."
    )
    data = model_json(prompt, images)
    score = float(data.get("score", 0))
    if not 0 <= score <= 10:
        raise RuntimeError("Model returned an invalid quality score.")
    return score, str(data.get("summary", ""))

def main():
    os.chdir(ROOT)
    dirty = run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    if dirty:
        raise RuntimeError("Working tree is not clean. Commit or stash local changes before running.")
    run(["git", "fetch", "origin"])
    original_branch = run(["git", "branch", "--show-current"], capture=True).stdout.strip()
    run(["git", "switch", "--detach", "origin/main"])
    branch = "ai/local-visual-loop-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    run(["git", "switch", "-c", branch])
    original_html = INDEX.read_text(encoding="utf-8")
    current_html = original_html
    accepted = 0
    stagnation = 0
    history = []
    try:
        images = screenshots()
        score, note = score_current(current_html, images)
        print(f"Initial visual score: {score:.1f}/10 — {note}")
        for iteration in range(1, MAX_ITERATIONS + 1):
            if score >= TARGET:
                print(f"Target reached: {score:.1f}/10 >= {TARGET}/10")
                break
            if stagnation >= 3:
                print("Stopping: three consecutive proposals failed to improve the measured score.")
                break
            print(f"\n=== Iteration {iteration}/{MAX_ITERATIONS} ===")
            proposal = ask_for_proposal(current_html, images, score)
            proposed_score = float(proposal.get("score", score))
            summary = str(proposal.get("summary", ""))
            if not proposal.get("changed", False):
                print("Model recommends no further change:", summary)
                break
            patch = proposal.get("css", "")
            if not valid_patch(patch):
                print("Rejected unsafe or malformed CSS proposal.")
                stagnation += 1
                continue
            before_html = current_html
            insertion = "\n<style id=\"local-ai-iteration-" + str(iteration) + "\">\n/* Local Ollama proposal; test-gated. */\n" + patch + "\n</style>\n"
            candidate_html = before_html.replace("</head>", insertion + "</head>", 1)
            INDEX.write_text(candidate_html, encoding="utf-8")
            try:
                images_after = screenshots()
                after_score, after_note = score_current(candidate_html, images_after)
                run(["git", "diff", "--check"])
            except Exception as exc:
                INDEX.write_text(before_html, encoding="utf-8")
                print("Rejected iteration after test/review failure:", exc)
                stagnation += 1
                images = screenshots()
                continue
            gain = after_score - score
            record = {"iteration": iteration, "before": score, "after": after_score,
                      "gain": gain, "summary": summary, "evaluation": after_note}
            history.append(record)
            if gain >= MIN_GAIN:
                current_html = candidate_html
                images = images_after
                score = after_score
                accepted += 1
                stagnation = 0
                print(f"ACCEPTED: {score:.1f}/10 (+{gain:.1f}). {summary}")
                if score >= TARGET:
                    print("Quality target reached.")
                    break
            else:
                INDEX.write_text(before_html, encoding="utf-8")
                print(f"REJECTED: score gain {gain:.1f} is below required {MIN_GAIN:.1f}. {after_note}")
                stagnation += 1
                images = screenshots()
        report = {"model": MODEL, "target": TARGET, "final_score": score,
                  "accepted_iterations": accepted, "history": history}
        (ROOT / "local-ai-review-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        if accepted == 0:
            INDEX.write_text(original_html, encoding="utf-8")
            print("No improvements passed validation. Nothing will be pushed.")
            return
        run(["git", "add", "index.html", "local-ai-review-report.json"])
        run(["git", "commit", "-m", "Apply validated local AI visual improvements"])
        run(["git", "push", "-u", "origin", branch])
        gh = run(["where.exe", "gh"], check=False, capture=True)
        compare = "https://github.com/prathameshmohod174/portfolio/compare/main..." + branch
        if gh.returncode == 0:
            pr = run(["gh", "pr", "create", "--draft", "--base", "main", "--head", branch,
                "--title", "Local AI visual improvements", "--body",
                f"Local Ollama iterative visual review. Accepted {accepted} improvement(s); final estimated score {score:.1f}/10; target {TARGET}/10. See local-ai-review-report.json. Playwright passed for accepted changes. No auto-merge."], check=False)
            if pr.returncode != 0:
                print("Draft PR creation failed. Compare:", compare)
        else:
            print("Branch pushed; install/authenticate GitHub CLI for automatic draft PR creation.")
            print("Compare:", compare)
        print(f"Finished: {score:.1f}/10; accepted {accepted} iteration(s); branch {branch}")
    finally:
        INDEX.write_text(current_html if accepted else original_html, encoding="utf-8")
        run(["git", "switch", original_branch], check=False)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("LOCAL VISUAL LOOP STOPPED:", exc, file=sys.stderr)
        sys.exit(1)
