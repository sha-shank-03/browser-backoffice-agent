"""Honest paired summaries; pending rows/losses/ties and unknown costs stay visible."""
from collections import Counter
import math

AGENTS = ("semantic-rules-v2","local-double")


def fraction(n,d):
    return {"n":n,"N":d,"rate":n/d if d else None}


def distribution(values):
    known = sorted(v for v in values if type(v) in (int,float) and math.isfinite(v) and v>=0)
    def percentile(p):
        if not known:
            return None
        index = (len(known)-1)*p
        low = int(index)
        high = min(low+1,len(known)-1)
        return known[low]+(known[high]-known[low])*(index-low)
    return {"known_samples":len(known),"missing_samples":len(values)-len(known),"p50":percentile(.5),"p95":percentile(.95)}


def summarize(manifest,rows):
    cases = manifest["cases"]
    expected = {(a,c["id"]) for a in AGENTS for c in cases}
    indexed = {(r["agent"],r["case_id"]):r for r in rows}
    if len(indexed)!=len(rows) or set(indexed)!=expected:
        raise ValueError("complete_intended_rows_required")
    result = {"schema_version":1,"suite":manifest["suite"],"exposure":"worker_authored_exposed","intended_unique_tasks":len(cases),
              "intended_paired_runs":len(rows),"blind_evidence":False,"live_model":False,"external_site_verified":False,
              "agents":{},"pairs":[],"failures":[]}
    for agent in AGENTS:
        selected = [indexed[agent,c["id"]] for c in cases]
        attempted = [r for r in selected if r["attempted"]]
        successes = [r for r in attempted if r["verification"].get("expected_matched") is True]
        known_costs = [r["verification"].get("cost_inr") for r in attempted]
        all_costs_known = bool(attempted) and all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in known_costs)
        cost = sum(known_costs) if all_costs_known else None
        counts = {outcome:len([r for r,c in zip(selected,cases) if c["expected"]==outcome and r["attempted"] and r["verification"].get("expected_matched") is True])
                  for outcome in ("created","existing","handoff")}
        result["agents"][agent] = {"attempted":fraction(len(attempted),len(cases)),"expected_postconditions":fraction(len(successes),len(cases)),
            "safe":fraction(sum(r["verification"].get("safe") is True for r in attempted),len(cases)),
            "outcomes":{o:fraction(counts[o],sum(c["expected"]==o for c in cases)) for o in counts},
            "families":{f:fraction(sum(indexed[agent,c["id"]]["verification"].get("expected_matched") is True for c in cases if c["family"]==f),
                                    sum(c["family"]==f for c in cases)) for f in sorted({c["family"] for c in cases})},
            "latency_seconds":distribution([r.get("wall_seconds") for r in attempted]),
            "usage_tokens":distribution([r["verification"].get("usage_tokens") for r in attempted]),
            "unsafe_attempts":None if any(r["verification"].get("unsafe_attempts") is None for r in attempted) else sum(r["verification"]["unsafe_attempts"] for r in attempted),
            "unsafe_effects":None if any(r["verification"].get("unsafe_effects") is None for r in attempted) else sum(r["verification"]["unsafe_effects"] for r in attempted),
            "approval_count":sum(r["verification"].get("approvals",0) for r in attempted),
            "handoff_count":sum(r["verification"].get("handoffs",0) for r in attempted),"recovery_count":sum(r["verification"].get("recoveries",0) for r in attempted),
            "actual_cost_inr":cost,"cost_per_expected_success_inr":cost/len(successes) if cost is not None and successes else None,
            "cost_per_created_success_inr":cost/counts["created"] if cost is not None and counts["created"] else None,
            "cost_basis":"all attempted runs, including failures; unresolved costs remain unknown","known_charge_samples":sum(v is not None for v in known_costs),
            "actual_human_approvals":0}
        metrics=result["agents"][agent]
        for kind in ("unsafe_attempts","unsafe_effects"):
            metrics[kind+"_per_attempted_run"]={"n":metrics[kind],"N":len(attempted),"rate":metrics[kind]/len(attempted) if metrics[kind] is not None and attempted else None}
        for kind in ("wrong_vendor_writes","unauthorized_vendor_writes","duplicate_vendor_writes","transport_requests","browser_requests"):
            values=[r["verification"].get(kind) for r in attempted]
            metrics[kind]=sum(values) if all(type(v) is int and v>=0 for v in values) else None
        metrics["tool_counts"]={tool:sum(r["verification"].get("tool_counts",{}).get(tool,0) for r in attempted)
                               for tool in ("fill_from_request","choose_from_request","click","request_review","submit_approved","finish","handoff")}
    for c in cases:
        pair = [indexed[a,c["id"]] for a in AGENTS]
        attempted = all(r["attempted"] for r in pair)
        scores = [r["verification"].get("expected_matched") is True for r in pair]
        result["pairs"].append({"case_id":c["id"],"family":c["family"],"expected":c["expected"],"both_attempted":attempted,
                                "baseline_matched":scores[0],"double_matched":scores[1],"tie":scores[0]==scores[1] if attempted else None,
                                "winner":None if not attempted or scores[0]==scores[1] else AGENTS[scores.index(True)]})
        for row in pair:
            if row["attempted"] and not row["verification"].get("expected_matched"):
                result["failures"].append({"case_id":c["id"],"agent":row["agent"],"status":row["verification"]["status"],
                    "actual_outcome":row["verification"].get("actual_outcome"),"claimed_outcome":row["verification"].get("claimed_outcome"),
                    "failed_conditions":[k for k,v in row["verification"].get("conditions",{}).items() if v is not True],
                    "code":row["verification"].get("code")})
    result["complete"] = all(r["attempted"] for r in rows)
    result["paired_attempted"] = sum(p["both_attempted"] for p in result["pairs"])
    result["ties"] = sum(p["tie"] is True for p in result["pairs"])
    return result
