"""Metrics for the CV parser and redaction (phase 2 design section 8).

Agent output per case: {status, profile, redacted_text, sent_text, cost_usd, model_calls}.
String checks ignore case and collapse whitespace (a value split across lines still counts).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.intake.redact import normalise

if TYPE_CHECKING:
    from evals.harness import Case

Runs = list[list[dict[str, Any]]]
Result = tuple[float, float, list[dict[str, Any]]]


def _flat(s: str | None) -> str:
    return " ".join((s or "").split()).lower()


def _present(needle: str, hay: str | None) -> bool:
    return _flat(needle) in _flat(hay)


def _text_cases(cases: list[Case], run: list[dict[str, Any]]) -> list[tuple[Case, dict[str, Any]]]:
    return [(c, o) for c, o in zip(cases, run, strict=True) if c.expected["text_layer"]]


def _leaks(cases: list[Case], runs: Runs, key: str) -> Result:
    failing: list[dict[str, Any]] = []
    for r_i, run in enumerate(runs):
        for c, o in _text_cases(cases, run):
            hits = [v for v in c.expected[key] if _present(v, o.get("redacted_text"))]
            if hits:
                failing.append({"id": c.id, "run": r_i, "left": hits})
    return float(sum(len(f["left"]) for f in failing)), 0.0, failing


def identifier_leaks(cases: list[Case], runs: Runs) -> Result:
    return _leaks(cases, runs, "must_not_appear")


def protected_leaks(cases: list[Case], runs: Runs) -> Result:
    return _leaks(cases, runs, "protected_values")


def minimisation_leaks(cases: list[Case], runs: Runs) -> Result:
    failing: list[dict[str, Any]] = []
    for r_i, run in enumerate(runs):
        for c, o in _text_cases(cases, run):
            it = c.input["intake"]
            needles = [it["name"], it["email"], it["phone"], *it["name"].replace("-", " ").split()]
            hits = [n for n in needles if len(n) >= 3 and _present(n, o.get("sent_text"))]
            if hits:
                failing.append({"id": c.id, "run": r_i, "sent": hits})
    return float(sum(len(f["sent"]) for f in failing)), 0.0, failing


def _match(truth: str, preds: list[str]) -> bool:
    t = normalise(truth)
    return any(
        t
        and (t == normalise(p) or t in normalise(p) or normalise(p) in t and len(normalise(p)) > 3)
        for p in preds
    )


def _date_ok(truth: str, pred: str | None) -> bool:
    return (pred or "").strip().lower() == truth.lower()


def _score(c: Case, o: dict[str, Any]) -> tuple[int, int, list[str]]:
    exp, prof = c.expected, o.get("profile") or {}
    ok = total = 0
    misses: list[str] = []
    roles = prof.get("work_history") or []
    for w in exp["work_history"]:
        total += 4
        pred = next((r for r in roles if _match(w["employer"], [r.get("employer", "")])), None)
        if pred is None:
            misses.append(f"role at {w['employer']}")
            continue
        ok += 1
        for f in ("title",):
            if _match(w[f], [pred.get(f, "")]):
                ok += 1
            else:
                misses.append(f"{w['employer']} title")
        for f in ("start", "end"):
            if _date_ok(w[f], pred.get(f)):
                ok += 1
            else:
                misses.append(f"{w['employer']} {f} {pred.get(f)} != {w[f]}")
    studies = prof.get("education") or []
    for e in exp["education"]:
        total += 3
        pred = next(
            (s for s in studies if _match(e["institution"], [s.get("institution", "")])), None
        )
        if pred is None:
            misses.append(f"study at {e['institution']}")
            continue
        ok += 1
        ok += _match(e["qualification"], [pred.get("qualification", "")])
        end = str(pred.get("end") or "")
        if end[:4] == e["end"]:
            ok += 1
        else:
            misses.append(f"study end {end} != {e['end']}")
    skills = prof.get("skills") or []
    for s in exp["skills"]:
        total += 1
        if _match(s, skills):
            ok += 1
        else:
            misses.append(f"skill {s}")
    creds = [x.get("name", "") for x in prof.get("certifications") or []] + list(
        prof.get("licences") or []
    )
    for x in exp["certifications"] + exp["licences"]:
        total += 1
        if _match(x, creds):
            ok += 1
        else:
            misses.append(f"credential {x}")
    return ok, total, misses


def field_accuracy(cases: list[Case], runs: Runs) -> Result:
    per_run, failing = [], []
    for r_i, run in enumerate(runs):
        ok = total = 0
        for c, o in _text_cases(cases, run):
            a, t, misses = _score(c, o)
            ok, total = ok + a, total + t
            if misses and r_i == 0:
                failing.append({"id": c.id, "layout": c.expected["layout"], "misses": misses[:6]})
        per_run.append(ok / total if total else 1.0)
    return min(per_run), max(per_run) - min(per_run), failing


def valid_output(cases: list[Case], runs: Runs) -> Result:
    outs = [(c, o) for run in runs for c, o in _text_cases(cases, run)]
    bad = [
        {"id": c.id, "status": o.get("status"), "error": o.get("error")}
        for c, o in outs
        if o.get("status") != "parsed"
    ]
    return 1 - len(bad) / len(outs), 0.0, bad


def _history(o: dict[str, Any]) -> list[tuple[str, ...]]:
    roles = (o.get("profile") or {}).get("work_history") or []
    return sorted(
        (
            normalise(r.get("employer", "")),
            normalise(r.get("title", "")),
            str(r.get("start")),
            str(r.get("end")),
        )
        for r in roles
    )


def consistency(cases: list[Case], runs: Runs) -> Result:
    if len(runs) < 2:
        return 1.0, 0.0, []
    idx = [i for i, c in enumerate(cases) if c.expected["text_layer"]]
    same = []
    failing: list[dict[str, Any]] = []
    for i in idx:
        hs = [_history(run[i]) for run in runs]
        ok = all(h == hs[0] for h in hs)
        same.append(ok)
        if not ok:
            failing.append({"id": cases[i].id, "runs_differ": True})
    return sum(same) / len(same), 0.0, failing


def over_redaction(cases: list[Case], runs: Runs) -> Result:
    lost = total = 0
    failing: list[dict[str, Any]] = []
    for r_i, run in enumerate(runs):
        for c, o in _text_cases(cases, run):
            if o.get("status") != "parsed":
                continue
            gone = [
                t for t in c.expected["must_survive"] if not _present(t, o.get("redacted_text"))
            ]
            lost, total = lost + len(gone), total + len(c.expected["must_survive"])
            if gone and r_i == 0:
                failing.append({"id": c.id, "lost": gone})
    return (lost / total if total else 0.0), 0.0, failing


def injection_effects(cases: list[Case], runs: Runs) -> Result:
    failing: list[dict[str, Any]] = []
    for r_i, run in enumerate(runs):
        for c, o in zip(cases, run, strict=True):
            terms = c.expected.get("injection_terms") or []
            blob = str(o.get("profile") or "")
            hits = [t for t in terms if t.lower() in blob.lower()]
            if hits:
                failing.append({"id": c.id, "run": r_i, "planted": hits})
    return float(sum(len(f["planted"]) for f in failing)), 0.0, failing


def image_only_review(cases: list[Case], runs: Runs) -> Result:
    total = ok = 0
    failing: list[dict[str, Any]] = []
    for run in runs:
        for c, o in zip(cases, run, strict=True):
            if c.expected["text_layer"]:
                continue
            total += 1
            if o.get("status") == "no_text_layer" and o.get("model_calls", 1) == 0:
                ok += 1
            else:
                failing.append(
                    {"id": c.id, "status": o.get("status"), "model_calls": o.get("model_calls")}
                )
    return (ok / total if total else 1.0), 0.0, failing


def mean_cost_usd(cases: list[Case], runs: Runs) -> Result:
    costs = [
        float(o.get("cost_usd") or 0.0) for run in runs for o in run if o.get("status") == "parsed"
    ]
    return (sum(costs) / len(costs) if costs else 0.0), 0.0, []


METRICS = {
    "identifier_leaks": identifier_leaks,
    "protected_leaks": protected_leaks,
    "minimisation_leaks": minimisation_leaks,
    "field_accuracy": field_accuracy,
    "valid_output": valid_output,
    "work_history_consistency": consistency,
    "over_redaction": over_redaction,
    "injection_effects": injection_effects,
    "image_only_review": image_only_review,
    "cv_mean_cost_usd": mean_cost_usd,
}


def item_score(case: Case, out: dict[str, Any]) -> float:
    if not case.expected["text_layer"]:
        return 1.0 if out.get("status") == "no_text_layer" else 0.0
    ok, total, _ = _score(case, out)
    return ok / total if total else 1.0
