"""Semantic-rules-v2: only immutable request and current public UI semantics.

Vocabulary below is development vocabulary. No case manifests, HTML field names,
fixture ids, gold outcomes, database or evaluator imports enter this policy.
"""
import re
import unicodedata

from backoffice.domain import Decision

FIELDS = ("legal_name","registration_ref","country","contact_email","category","payment_terms")
PHRASES = {
    "legal_name":("legal name","business name","registered organisation","registered business name","supplier legal identity"),
    "registration_ref":("registration reference","business identity reference","vendor reference","supplier registration identifier"),
    "country":("country","jurisdiction of operation","operating jurisdiction"),
    "contact_email":("contact email","correspondence email","vendor email","onboarding correspondence address"),
    "category":("category","supply classification","purchasing classification"),
    "payment_terms":("payment terms","invoice terms","settlement schedule","invoice settlement schedule"),
}
OPTION_SETS = {"country":{"IN","GB","US"},"category":{"Office supplies","IT services"},"payment_terms":{"NET30","NET60"}}
ANCHORS = {
    "legal_name":({"business","name"},{"supplier","identity"},{"registered","organisation"}),
    "registration_ref":({"registration","reference"},{"business","reference"},{"registration","identifier"}),
    "country":({"operating","jurisdiction"},),
    "contact_email":({"correspondence","address"},{"contact","email"},{"purchasing","email"}),
    "category":({"supply","classification"},{"purchasing","classification"}),
    "payment_terms":({"invoice","schedule"},{"invoice","settlement"},{"payment","terms"}),
}
CONTROL_KEYS = {"ref","role","label","value","options","description","context","required"}


def norm(value):
    value = unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+",value))


class SemanticRules:
    """State retains only publicly opened section labels; fresh refs are never cached."""
    name = "semantic-rules-v2"

    def __init__(self):
        self.opened_sections = set()

    def decide(self,context):
        if set(context) != {"request","observation","state"}:
            raise ValueError("public_context_only")
        observation,request,state = context["observation"],context["request"],context["state"]
        if set(observation) != {"id","path","title","text","controls","records"} or set(request) != set(FIELDS):
            raise ValueError("public_observation_only")
        if set(state) != {"approval_state","search_complete","commit_dispatched","commit_uncertain"}:
            raise ValueError("public_state_only")
        controls = observation["controls"]
        if any(set(c)-CONTROL_KEYS for c in controls):
            raise ValueError("hidden_control_metadata")
        def action(tool,**arguments):
            return Decision.parse({"tool":tool,"arguments":arguments})
        def handoff(reason="insufficient_evidence"):
            return action("handoff",reason=reason)
        def find(words,roles={"button","link"}):
            found = [c for c in controls if c["role"] in roles and any(norm(c["label"])==norm(w) for w in words)]
            return found[0] if len(found)==1 else None
        def click(words):
            c = find(words)
            return action("click",ref=c["ref"]) if c else handoff("unexpected_ui")
        path = observation["path"]
        if state["commit_uncertain"]:
            return handoff("uncertain_commit")
        if path == "/login":
            self.opened_sections.clear()
            return click(("Open fictional operator session",))
        if path == "/vendors":
            self.opened_sections.clear()
            search = find(("Registration reference search",),{"textbox"})
            if search is None:
                return handoff("unexpected_ui")
            if not state["search_complete"]:
                return (action("fill_from_request",ref=search["ref"],field="registration_ref")
                        if search["value"] != request["registration_ref"] else click(("Search",)))
            if observation["records"]:
                return (action("finish",outcome="existing") if observation["records"]==[request]
                        else handoff("conflicting_existing"))
            return click(("Register a vendor",))
        if path == "/vendors/new":
            mapped = {}
            for c in controls:
                if c["role"] not in {"textbox","combobox"}:
                    continue
                scores = {}
                label,description = norm(c["label"]),norm(c.get("description",""))
                for field,phrases in PHRASES.items():
                    score = max([0]+[3 if norm(p) in label else 2 if norm(p) in description else 0 for p in phrases])
                    if any(anchor<=set(label.split()) for anchor in ANCHORS[field]):score=max(score,3)
                    if any(anchor<=set(description.split()) for anchor in ANCHORS[field]):score=max(score,2)
                    if c["role"]=="combobox" and field in OPTION_SETS:
                        options = {o["value"] for o in c["options"] if o["value"]}
                        if options == OPTION_SETS[field] and (score or norm(c.get("context","")) in {"purchasing details","organisation details"}):
                            score = max(score,1)
                    if score:
                        scores[field] = score
                if not scores:
                    if c.get("required",True):
                        return handoff("unsupported_required_field")
                    continue
                maximum = max(scores.values())
                candidates = [f for f,s in scores.items() if s==maximum]
                if len(candidates)!=1 or candidates[0] in mapped:
                    return handoff("insufficient_evidence")
                field = candidates[0]
                if c["role"] != ("combobox" if field in OPTION_SETS else "textbox"):
                    return handoff("unexpected_ui")
                mapped[field] = c
            for field in FIELDS:
                if field in mapped and mapped[field]["value"] != request[field]:
                    c = mapped[field]
                    if field in OPTION_SETS and request[field] not in {o["value"] for o in c["options"]}:
                        return handoff("validation_rejected")
                    return action("choose_from_request" if field in OPTION_SETS else "fill_from_request",ref=c["ref"],field=field)
            if set(mapped) != set(FIELDS):
                sections = [c for c in controls if c["role"]=="button" and norm(c["label"]) in {"organisation details","purchasing details"}
                            and norm(c["label"]) not in self.opened_sections]
                if sections:
                    selected = sections[0]
                    self.opened_sections.add(norm(selected["label"]))
                    return action("click",ref=selected["ref"])
                return handoff()
            return click(("Review vendor",))
        if path == "/vendors/validation":
            return click(("Continue to review",)) if find(("Continue to review",)) else handoff("validation_rejected")
        if path == "/vendors/review":
            return action("submit_approved" if state["approval_state"]=="APPROVED" else "request_review",observation_id=observation["id"])
        if path == "/vendors/detail" and observation["records"]==[request] and state["commit_dispatched"]:
            return action("finish",outcome="created")
        return handoff()
