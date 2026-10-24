"""Literal source tracing, deliberately distinct from scientific verification."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import html
import re

from src.ai_workflow.schemas import PaperExtractionReport


CLAIM_FIELDS = (
    "problem_type", "math_model.sets_and_indices", "math_model.parameters",
    "math_model.decision_variables", "math_model.objectives", "math_model.constraints",
    "rl_formulation.state_space", "rl_formulation.action_space", "rl_formulation.action_masking",
    "rl_formulation.reward_function", "rl_formulation.network_architecture",
)


def _claims(report):
    data = report.model_dump()
    for field in CLAIM_FIELDS:
        value = data
        for key in field.split("."):
            value = value[key]
        entries = enumerate(value) if isinstance(value, list) else [(None, value)]
        for index, text in entries:
            if text.strip() and not text.lstrip().startswith(("[缺失", "缺失", "未核实", "[项目底座", "[待核实")):
                yield field, index, text


def _find_quote(text, reference, visible_end):
    quote = reference.quote
    if len(quote.strip()) < 12:
        return "invalid", [], "quote_too_short"
    if reference.source_start is not None:
        start = reference.source_start
        if start + len(quote) <= visible_end and text[start:start + len(quote)] == quote:
            return "located_unreviewed", [start], ""
        return "invalid", [], "offset_or_context_mismatch"
    positions = []
    position = text.find(quote, 0, visible_end)
    while position != -1 and len(positions) < 2:
        positions.append(position)
        position = text.find(quote, position + 1, visible_end)
    if not positions:
        return "invalid", [], "quote_not_in_target_context"
    if len(positions) > 1:
        return "ambiguous", [], "repeated_text_requires_source_start"
    return "located_unreviewed", positions, ""


def _location(text, quote, start, source_map):
    end = start + len(quote)
    pages = source_map.get("pages", [])
    in_pdf = bool(pages) and pages[0]["start"] <= start and end <= pages[-1]["end"]
    overlapping = [page["page"] for page in pages if page["start"] < end and page["end"] > start] if in_pdf else []
    return {"quote": quote, "start": start, "end": end,
            "source_path": source_map.get("pdf_source_path", "") if overlapping else source_map.get("source_path", ""),
            "source_kind": "pdf_text" if overlapping else "resolved_text",
            "line_start": text.count("\n", 0, start) + 1,
            "line_end": text.count("\n", 0, end - 1) + 1,
            "page_start": min(overlapping) if overlapping else None,
            "page_end": max(overlapping) if overlapping else None}


def audit_claim_evidence(
    report: PaperExtractionReport, text: str, *, source_map: dict | None = None,
    visible_limit: int | None = None,
) -> PaperExtractionReport:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_map = source_map or {"source_path": "", "source_kind": "text", "text_sha256": digest,
                                "text_length": len(text), "pages": [], "warnings": []}
    if source_map["text_sha256"] != digest or source_map["text_length"] != len(text):
        raise ValueError("Source map does not match the audited text")
    if visible_limit is not None and (type(visible_limit) is not int or visible_limit < 0):
        raise ValueError("visible_limit must be a non-negative character count")
    visible_end = min(len(text), visible_limit) if visible_limit is not None else len(text)
    claims = list(_claims(report))
    targets = {(field, index) for field, index, _ in claims}
    references = defaultdict(list)
    rejected = []
    for reference in report.claim_evidence:
        target = (reference.field, reference.item_index)
        if target not in targets:
            rejected.append({**reference.model_dump(), "reason": "unknown_claim_field_or_index"})
        else:
            references[target].append(reference)
    audited = []
    for field, index, claim in claims:
        entries = references[(field, index)]
        statuses, locations, errors = [], [], []
        for reference in entries:
            status, positions, error = _find_quote(text, reference, visible_end)
            statuses.append(status)
            errors.extend([error] if error else [])
            locations.extend(_location(text, reference.quote, position, source_map) for position in positions)
        status = ("missing" if not entries else "invalid" if "invalid" in statuses
                  else "ambiguous" if "ambiguous" in statuses else "located_unreviewed")
        audited.append({"field": field, "item_index": index, "claim": claim, "status": status,
                        "locations": locations, "errors": errors})
    counts = Counter(item["status"] for item in audited)
    report.evidence_status = "unverified"
    report.source_quotes = [quote for quote in report.source_quotes if quote and quote in text[:visible_end]]
    report.evidence_audit = {
        "source": source_map, "context_start": 0, "context_end": visible_end,
        "claims": audited, "rejected_references": rejected,
        "summary": {"claims_total": len(audited), "claims_located": counts["located_unreviewed"],
                    "counts": dict(counts), "rejected_references": len(rejected),
                    "all_claims_located": bool(audited) and counts["located_unreviewed"] == len(audited) and not rejected,
                    "status": "no_claims" if not audited else "text_locations_only"},
        "notice": "Exact text location is not proof of entailment, formula correctness, or scientific verification.",
    }
    return report


def _cell(value):
    text = html.escape(str(value), quote=True)
    text = re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", text)
    return text.replace("\r", "").replace("\n", "<br>")


def render_evidence_audit(audit: dict) -> list[str]:
    if not audit:
        return []
    source = audit.get("source", {})
    summary = audit.get("summary", {})
    lines = ["## 逐项原文证据", "",
             "仅核对原文片段及位置，不证明片段支持陈述，也不证明公式正确；仍须人工核实。",
             f"- 文本 SHA-256：{_cell(source.get('text_sha256', ''))}",
             f"- 来源：{_cell(source.get('source_path', '') or '仅有输入文本快照')}",
             f"- 模型可见字符区间：{audit.get('context_start', 0)}–{audit.get('context_end', 0)}（末端不含）",
             f"- 陈述数：{summary.get('claims_total', 0)}；定位到文本：{summary.get('claims_located', 0)}；状态：{summary.get('status', 'unknown')}",
             "", "| 字段 | 陈述 | 文本状态 | 位置 | 原文片段与诊断 |", "|---|---|---|---|---|"]
    for claim in audit.get("claims", []):
        target = claim["field"] + (f"[{claim['item_index']}]" if claim["item_index"] is not None else "")
        places, quotes = [], []
        for location in claim["locations"]:
            place = f"行 {location['line_start']}–{location['line_end']}；字符 [{location['start']}, {location['end']})"
            if location["page_start"] is not None:
                place += f"；PDF 页 {location['page_start']}–{location['page_end']}"
            places.append(place)
            quotes.append(location["quote"])
        diagnostic = "\n".join([*quotes, *claim["errors"]]) or "缺少逐项原文依据"
        cells = [_cell(value) for value in (target, claim["claim"], claim["status"], "\n".join(places) or "—", diagnostic)]
        status = claim["status"] if claim["status"] in {"located_unreviewed", "missing", "invalid", "ambiguous"} else "unknown"
        cells[2] = f"`{status}`"
        lines.append("| " + " | ".join(cells) + " |")
    for reference in audit.get("rejected_references", []):
        lines.append(f"- 拒绝的引用：{_cell(reference['field'])} / {_cell(reference.get('item_index'))}：{_cell(reference['reason'])}")
    lines.extend(f"- 来源提示：{_cell(warning)}" for warning in source.get("warnings", []))
    return [*lines, ""]
