import base64, json, os, re, subprocess, sys, urllib.request, urllib.error
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
GENERIC_TITLE = re.compile(
    r"^(selected film|long-form video project|editing study|editing reel collection)(?:\s*(?:[-—/]\s*)?\d+)?$",
    re.I
)

def run(args, check=True, capture=False):
    print("+", " ".join(str(x) for x in args), flush=True)
    return subprocess.run(args, cwd=ROOT, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None)

def screenshots():
    run(["npm.cmd", "run", "test:chromium"])
    paths = [SHOTS / "desktop.png", SHOTS / "mobile.png"]
    if not all(p.exists() for p in paths):
        raise RuntimeError("Playwright did not create both desktop and mobile screenshots.")
    return [base64.b64encode(p.read_bytes()).decode("ascii") for p in paths]

def model_json(prompt, images):
    payload = {"model": MODEL, "stream": False, "format": "json",
        "messages": [{"role": "user", "content": prompt, "images": images}],
        "options": {"temperature": 0.1, "num_predict": 900}}
    req = urllib.request.Request(API, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail[:1200]}") from exc
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

def portfolio_audit(html):
    cards = re.findall(
        r"<article\b(?=[^>]*\bclass\s*=\s*['\"][^'\"]*\bcard\b[^'\"]*['\"])[^>]*>.*?</article>",
        html, re.I | re.S
    )
    titles = []
    media_cards = 0
    linked_cards = 0
    missing_role_cards = 0
    for card in cards:
        heading = re.search(r"<h3\b[^>]*>(.*?)</h3>", card, re.I | re.S)
        title = re.sub(r"<[^>]+>", "", heading.group(1)).strip() if heading else ""
        titles.append(title)
        if re.search(r"<(?:img|video|picture|iframe)\b", card, re.I):
            media_cards += 1
        if re.search(r"<a\b[^>]*href\s*=\s*['\"]https?://", card, re.I):
            linked_cards += 1
        if not re.search(r"<(?:div|p|span)\b[^>]*class\s*=\s*['\"][^'\"]*\btag\b", card, re.I):
            missing_role_cards += 1

    generic_titles = [title for title in titles if GENERIC_TITLE.match(title)]
    blockers = []
    media_threshold = min(3, len(cards))
    if cards and media_cards < media_threshold:
        blockers.append(
            f"Real media appears in {media_cards}/{len(cards)} project cards; "
            f"at least {media_threshold} cards need actual image/video media rather than CSS-only placeholders."
        )
    if len(generic_titles) >= 2:
        blockers.append(
            f"{len(generic_titles)} project cards use generic titles ({', '.join(generic_titles[:4])}); "
            "give each project a specific, accurate name."
        )
    if cards and linked_cards < len(cards):
        blockers.append(f"{len(cards) - linked_cards} project cards have no external source link.")
    if missing_role_cards:
        blockers.append(f"{missing_role_cards} project cards lack a visible role/category label.")

    return {
        "project_cards": len(cards),
        "cards_with_real_media": media_cards,
        "cards_with_external_links": linked_cards,
        "cards_with_role_labels": len(cards) - missing_role_cards,
        "generic_titles": generic_titles,
        "blockers": blockers,
    }

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

def rubric_text(criteria):
    if not isinstance(criteria, dict):
        return "Criteria scores unavailable."
    keys = [
        ("imagery", "Imagery / real project evidence"),
        ("differentiation", "Project differentiation"),
        ("completeness", "Portfolio completeness"),
        ("mobile", "Mobile composition"),
        ("legibility", "Typography and legibility"),
        ("identity", "Cinematic identity"),
    ]
    return "; ".join(
        f"{label}: {criteria.get(key, 'unscored')}/10" for key, label in keys
    )

def ask_for_proposal(html, images, current_score, criteria, audit):
    prompt = (
        "You are a rigorous senior web designer reviewing the Random Hours creative portfolio. "
        "Review attached screenshots (desktop then mobile), the six rubric scores, and the deterministic HTML audit. "
        f"Current aesthetic score: {current_score}/10. Rubric: {rubric_text(criteria)}. "
        "HTML audit (treat as factual): " + json.dumps(audit, ensure_ascii=False) + ". "
        "Return ONLY JSON: {\"score\": number, \"changed\": boolean, \"summary\": string, \"css\": string}. "
        "Propose one high-impact CSS-only improvement only if it improves a named criterion visible in the screenshots. "
        "At most 5 simple CSS rules, under 1800 chars. No at-rules, url(), external assets, scripts, HTML, or selectors html/body/:root/*. "
        "CSS cannot resolve audit blockers such as missing real media or generic project titles. Never claim it can. "
        "If no meaningful CSS improvement is available, return changed=false. Do not propose cosmetic churn or extra glow. "
        "The 8.5/10 target is considered achieved only when the aesthetic score reaches the target AND the audit has no blockers. "
        "If the score is already at target but blockers remain, only propose a genuinely useful CSS improvement; otherwise changed=false. "
        "Current CSS follows:\n" + css_now(html)[:9000]
    )
    return model_json(prompt, images)

def score_current(html, images):
    audit = portfolio_audit(html)
    prompt = (
        "Assess the Random Hours portfolio using the attached desktop and mobile screenshots. "
        "Return ONLY JSON with this shape: "
        "{\"score\": number, \"summary\": string, \"criteria\": "
        "{\"imagery\": number, \"differentiation\": number, \"completeness\": number, "
        "\"mobile\": number, \"legibility\": number, \"identity\": number}}. "
        "Score each criterion from 1 to 10. imagery means actual project image/video evidence, not gradients or decorative backgrounds. "
        "differentiation means whether projects are distinct and identifiable. completeness means whether a visitor can understand "
        "the work and role credits. mobile means small-screen composition. legibility means hierarchy and readability. "
        "identity means cinematic coherence. Score conservatively and do not infer assets or project details not present. "
        "The deterministic HTML audit is factual and must influence imagery, differentiation, and completeness scores: "
        + json.dumps(audit, ensure_ascii=False)
    )
    data = model_json(prompt, images)
    score = float(data.get("score", 0))
    if not 0 <= score <= 10:
        raise RuntimeError("Model returned an invalid quality score.")
    raw_criteria = data.get("criteria", {})
    criteria = {}
    for key in ("imagery", "differentiation", "completeness", "mobile", "legibility", "identity"):
        try:
            value = float(raw_criteria.get(key, score))
        except (TypeError, ValueError):
            value = score
        criteria[key] = max(0.0, min(10.0, value))
    return score, str(data.get("summary", "")), criteria, audit

def evaluated_score(aesthetic_score, audit):
    # Gate the target, not CSS iteration gains: content blockers must not make visual progress impossible.
    score = aesthetic_score
    if audit["cards_with_real_media"] < min(3, audit["project_cards"]) and audit["project_cards"]:
        score = min(score, 7.0)
    if len(audit["generic_titles"]) >= 2:
        score = min(score, 7.5)
    return score

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
        score, note, criteria, audit = score_current(current_html, images)
        gated_score = evaluated_score(score, audit)
        print(f"Initial aesthetic score: {score:.1f}/10; readiness-adjusted score: {gated_score:.1f}/10 — {note}")
        print("Rubric:", rubric_text(criteria))
        if audit["blockers"]:
            print("Portfolio-readiness blockers:")
            for blocker in audit["blockers"]:
                print(" -", blocker)
        for iteration in range(1, MAX_ITERATIONS + 1):
            gated_score = evaluated_score(score, audit)
            if gated_score >= TARGET and not audit["blockers"]:
                print(f"Target reached: {gated_score:.1f}/10 >= {TARGET}/10 and no readiness blockers remain.")
                break
            if stagnation >= 3:
                print("Stopping: three consecutive proposals failed to improve the evaluated score.")
                break
            print(f"\n=== Iteration {iteration}/{MAX_ITERATIONS} ===")
            proposal = ask_for_proposal(current_html, images, score, criteria, audit)
            summary = str(proposal.get("summary", ""))
            if not proposal.get("changed", False):
                print("Model recommends no further useful CSS change:", summary)
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
                after_score, after_note, after_criteria, after_audit = score_current(candidate_html, images_after)
                run(["git", "diff", "--check"])
            except Exception as exc:
                INDEX.write_text(before_html, encoding="utf-8")
                print("Rejected iteration after test/review failure:", exc)
                stagnation += 1
                images = screenshots()
                continue
            gain = after_score - score
            record = {
                "iteration": iteration, "before_aesthetic_score": score, "after_aesthetic_score": after_score,
                "before_readiness_score": evaluated_score(score, audit),
                "after_readiness_score": evaluated_score(after_score, after_audit), "aesthetic_gain": gain,
                "summary": summary, "evaluation": after_note, "criteria": after_criteria,
                "readiness_audit": after_audit
            }
            history.append(record)
            if gain >= MIN_GAIN:
                current_html = candidate_html
                images = images_after
                score, criteria, audit = after_score, after_criteria, after_audit
                accepted += 1
                stagnation = 0
                print(f"ACCEPTED: {score:.1f}/10 (+{gain:.1f}). {summary}")
                print("Rubric:", rubric_text(criteria))
                if audit["blockers"]:
                    print("Still blocked from target:")
                    for blocker in audit["blockers"]:
                        print(" -", blocker)
                gated_score = evaluated_score(score, audit)
                if gated_score >= TARGET and not audit["blockers"]:
                    print("Quality target reached with all readiness gates passing.")
                    break
            else:
                INDEX.write_text(before_html, encoding="utf-8")
                print(f"REJECTED: evaluated score gain {gain:.1f} is below required {MIN_GAIN:.1f}. {after_note}")
                stagnation += 1
                images = screenshots()
        gated_score = evaluated_score(score, audit)
        target_reached = gated_score >= TARGET and not audit["blockers"]
        report = {
            "model": MODEL, "target": TARGET, "final_aesthetic_score": score,
            "final_readiness_adjusted_score": gated_score, "target_reached": target_reached,
            "accepted_iterations": accepted, "criteria": criteria, "readiness_audit": audit, "history": history
        }
        report_path = (ROOT / "local-ai-review-report.json") if accepted else (ROOT.parent / "local-ai-review-report.json")
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if accepted == 0:
            INDEX.write_text(original_html, encoding="utf-8")
            run(["git", "switch", original_branch], check=False)
            run(["git", "branch", "-D", branch], check=False)
            print("No CSS improvements passed validation. No code changes will be pushed.")
            print(f"Review report saved outside the repository to {report_path}.")
            if not target_reached and audit["blockers"]:
                print("The target remains unmet because CSS-only changes cannot resolve the readiness blockers.")
            return
        run(["git", "add", "index.html", "local-ai-review-report.json"])
        run(["git", "commit", "-m", "Apply validated local AI visual improvements"])
        run(["git", "push", "-u", "origin", branch])
        gh = run(["where.exe", "gh"], check=False, capture=True)
        compare = "https://github.com/prathameshmohod174/portfolio/compare/main..." + branch
        if gh.returncode == 0:
            pr = run(["gh", "pr", "create", "--draft", "--base", "main", "--head", branch,
                "--title", "Local AI visual improvements", "--body",
                f"Local Ollama iterative visual review. Accepted {accepted} improvement(s); aesthetic score {score:.1f}/10; readiness-adjusted score {gated_score:.1f}/10; target {TARGET}/10; readiness gates {'passed' if target_reached else 'not all passed'}. See local-ai-review-report.json. Playwright passed for accepted changes. No auto-merge."], check=False)
            if pr.returncode != 0:
                print("Draft PR creation failed. Compare:", compare)
        else:
            print("Branch pushed; install/authenticate GitHub CLI for automatic draft PR creation.")
            print("Compare:", compare)
        print(f"Finished: aesthetic {score:.1f}/10; readiness-adjusted {gated_score:.1f}/10; accepted {accepted} iteration(s); target reached={target_reached}; branch {branch}")
    finally:
        if accepted == 0:
            INDEX.write_text(original_html, encoding="utf-8")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("LOCAL VISUAL LOOP STOPPED:", exc, file=sys.stderr)
        sys.exit(1)
