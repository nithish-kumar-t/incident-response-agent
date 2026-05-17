"""
PDF incident report generator.
Takes the full pipeline result and renders a professional HTML → PDF report.
"""
import json
import logging
from datetime import datetime, timezone

from weasyprint import HTML

logger = logging.getLogger(__name__)

_SEVERITY_COLORS = {
    "critical": "#e74c3c",
    "high":     "#e67e22",
    "medium":   "#f39c12",
    "low":      "#27ae60",
}

_SEVERITY_BG = {
    "critical": "#fdf0ef",
    "high":     "#fef5ec",
    "medium":   "#fefaec",
    "low":      "#edfaf3",
}


def _severity_color(severity: str) -> str:
    return _SEVERITY_COLORS.get(severity.lower(), "#7f8c8d")


def _severity_bg(severity: str) -> str:
    return _SEVERITY_BG.get(severity.lower(), "#f4f4f4")


def _escape(text: str) -> str:
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _render_list(items: list) -> str:
    if not items:
        return "<p style='color:#888;'>None</p>"
    return "<ul style='margin:4px 0; padding-left:20px;'>" + \
           "".join(f"<li>{_escape(str(i))}</li>" for i in items) + \
           "</ul>"


def _render_code(text: str) -> str:
    if not text:
        return "<p style='color:#888;'>—</p>"
    return f"<pre style='background:#1e1e2e;color:#cdd6f4;padding:14px;border-radius:6px;font-size:11px;white-space:pre-wrap;overflow-wrap:break-word;'>{_escape(text)}</pre>"


def _build_html(result: dict) -> str:
    triage     = result.get("triage", {})
    invest     = result.get("investigation", {})
    code       = result.get("code_analysis", {})
    pid        = result.get("pipeline_id", "—")
    started    = result.get("started_at", "")
    completed  = result.get("completed_at", "")

    severity   = (triage.get("severity") or "unknown").lower()
    svc        = _escape(triage.get("service_name") or triage.get("service") or "unknown")
    alert      = _escape(triage.get("error_summary") or triage.get("error_message") or "")
    err_type   = _escape(triage.get("error_type") or "")
    key_inds   = triage.get("key_indicators") or []
    actions    = triage.get("actions_taken") or []

    hypothesis = _escape(invest.get("root_cause_hypothesis") or invest.get("hypothesis") or "—")
    confidence = _escape(invest.get("confidence") or "—")
    inference  = _escape(invest.get("inference") or invest.get("analysis") or "—")
    stack      = invest.get("stack_trace") or ""

    root_cause = _escape(code.get("root_cause") or "—")
    fix        = _escape(code.get("fix_suggestion") or code.get("fix") or "—")
    depth      = _escape(code.get("analysis_depth") or "—")
    complexity = _escape(code.get("complexity_assessment") or "—")
    next_steps = code.get("recommended_next_steps") or code.get("next_steps") or []
    alt_sol    = code.get("alternative_solutions") or []
    aff_code   = code.get("affected_code") or []

    # Fallback: if structured fields are missing, show raw LLM output in the PDF
    triage_raw = triage.get("raw_output", "")
    invest_raw = invest.get("raw_output", "")
    code_raw   = code.get("raw_output", "")

    sev_color  = _severity_color(severity)
    sev_bg     = _severity_bg(severity)

    affected_code_html = ""
    for ac in aff_code:
        affected_code_html += f"""
        <div style="margin-bottom:12px; border-left:3px solid {sev_color}; padding-left:12px;">
            <div style="font-family:monospace; font-size:12px; color:#555;">
                {_escape(ac.get('file',''))}:{ac.get('line','')}
            </div>
            {_render_code(ac.get('snippet',''))}
            <div style="color:#c0392b; font-size:12px; margin-top:4px;">
                &#x26A0; {_escape(ac.get('issue',''))}
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Helvetica, Arial, sans-serif; color: #1a1a2e; background: #fff; font-size: 13px; }}

  .header {{ background: #1a1a2e; color: white; padding: 32px 40px 24px; }}
  .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; }}
  .header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
  .header .sub {{ font-size: 13px; color: #a0aec0; }}
  .badge {{ display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 12px;
             font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;
             background: {sev_color}; color: white; }}
  .meta-bar {{ background: #f8f9fa; border-bottom: 1px solid #e2e8f0; padding: 12px 40px;
               display: flex; gap: 40px; }}
  .meta-item {{ font-size: 12px; }}
  .meta-item .label {{ color: #718096; margin-bottom: 2px; }}
  .meta-item .value {{ font-weight: 600; color: #1a1a2e; }}

  .content {{ padding: 28px 40px; }}
  .section {{ margin-bottom: 28px; }}
  .section-header {{ display: flex; align-items: center; gap: 10px;
                     border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 14px; }}
  .section-header h2 {{ font-size: 15px; font-weight: 700; color: #1a1a2e; }}
  .section-num {{ width: 24px; height: 24px; border-radius: 50%; background: {sev_color};
                  color: white; font-size: 12px; font-weight: 700;
                  display: flex; align-items: center; justify-content: center; }}

  .card {{ background: #f8f9fa; border: 1px solid #e2e8f0; border-radius: 8px;
            padding: 14px 16px; margin-bottom: 10px; }}
  .card.highlight {{ background: {sev_bg}; border-color: {sev_color}; }}
  .card-label {{ font-size: 11px; color: #718096; text-transform: uppercase;
                  letter-spacing: 0.5px; margin-bottom: 4px; }}
  .card-value {{ font-size: 13px; color: #1a1a2e; line-height: 1.5; }}

  .two-col {{ display: flex; gap: 12px; }}
  .two-col .card {{ flex: 1; }}

  .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
           background: #e2e8f0; color: #4a5568; margin: 2px; }}

  .confidence-high {{ color: #27ae60; font-weight: 700; }}
  .confidence-medium {{ color: #e67e22; font-weight: 700; }}
  .confidence-low {{ color: #e74c3c; font-weight: 700; }}
  .confidence-\\2014  {{ color: #718096; font-weight: 700; }}

  .fix-box {{ background: #edfaf3; border: 1px solid #27ae60; border-radius: 8px;
               padding: 14px 16px; }}
  .fix-box .fix-label {{ color: #1e8449; font-size: 11px; font-weight: 700;
                          text-transform: uppercase; margin-bottom: 6px; }}

  .footer {{ margin-top: 32px; padding: 16px 40px; background: #f8f9fa;
              border-top: 1px solid #e2e8f0; text-align: center;
              font-size: 11px; color: #a0aec0; }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-top">
    <div>
      <h1>Incident Report</h1>
      <div class="sub">Pipeline ID: {pid}</div>
    </div>
    <div class="badge">{severity}</div>
  </div>
</div>

<!-- META BAR -->
<div class="meta-bar">
  <div class="meta-item">
    <div class="label">Service</div>
    <div class="value">{svc}</div>
  </div>
  <div class="meta-item">
    <div class="label">Error Type</div>
    <div class="value">{err_type}</div>
  </div>
  <div class="meta-item">
    <div class="label">Started</div>
    <div class="value">{started}</div>
  </div>
  <div class="meta-item">
    <div class="label">Completed</div>
    <div class="value">{completed}</div>
  </div>
  <div class="meta-item">
    <div class="label">Analysis Depth</div>
    <div class="value">{depth} / {complexity}</div>
  </div>
</div>

<div class="content">

  <!-- SECTION 1: TRIAGE -->
  <div class="section">
    <div class="section-header">
      <div class="section-num">1</div>
      <h2>Triage</h2>
    </div>

    <div class="card highlight">
      <div class="card-label">Error Summary</div>
      <div class="card-value">{alert}</div>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-label">Key Indicators</div>
        <div class="card-value">{_render_list(key_inds) if key_inds else ("<p style='color:#888;'>—</p>" if not triage_raw else "")}</div>
      </div>
      <div class="card">
        <div class="card-label">Actions Taken</div>
        <div class="card-value">{_render_list(actions) if actions else ("<p style='color:#888;'>—</p>" if not triage_raw else "")}</div>
      </div>
    </div>
    {"<div class='card'><div class='card-label'>Agent Output</div><div class='card-value'>" + _render_code(triage_raw) + "</div></div>" if triage_raw and not alert else ""}
  </div>

  <!-- SECTION 2: INVESTIGATION -->
  <div class="section">
    <div class="section-header">
      <div class="section-num">2</div>
      <h2>Investigation</h2>
    </div>

    <div class="two-col">
      <div class="card">
        <div class="card-label">Root Cause Hypothesis</div>
        <div class="card-value">{hypothesis}</div>
      </div>
      <div class="card">
        <div class="card-label">Confidence</div>
        <div class="card-value confidence-{confidence.lower()}">{confidence.upper()}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-label">Inference</div>
      <div class="card-value">{inference}</div>
    </div>

    {"<div class='card'><div class='card-label'>Stack Trace</div><div class='card-value'>" + _render_code(stack) + "</div></div>" if stack else ""}
    {"<div class='card'><div class='card-label'>Agent Output</div><div class='card-value'>" + _render_code(invest_raw) + "</div></div>" if invest_raw and not hypothesis or hypothesis == "—" else ""}
  </div>

  <!-- SECTION 3: CODE ANALYSIS -->
  <div class="section">
    <div class="section-header">
      <div class="section-num">3</div>
      <h2>Code Analysis</h2>
    </div>

    <div class="card highlight">
      <div class="card-label">Root Cause</div>
      <div class="card-value">{root_cause}</div>
    </div>

    {"<div>" + affected_code_html + "</div>" if aff_code else ""}

    <div class="fix-box">
      <div class="fix-label">&#x25B6; Fix Suggestion</div>
      <div class="card-value">{fix}</div>
    </div>

    {"<div class='card' style='margin-top:10px;'><div class='card-label'>Alternative Solutions</div><div class='card-value'>" + _render_list(alt_sol) + "</div></div>" if alt_sol else ""}
    {"<div class='card' style='margin-top:10px;'><div class='card-label'>Agent Output</div><div class='card-value'>" + _render_code(code_raw) + "</div></div>" if code_raw and root_cause == "—" else ""}

    <div class="card" style="margin-top:10px;">
      <div class="card-label">Recommended Next Steps</div>
      <div class="card-value">{_render_list(next_steps)}</div>
    </div>
  </div>

</div>

<div class="footer">
  Generated by Incident Response Agent &mdash; {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
</div>

</body>
</html>"""


def generate_pdf(pipeline_result: dict) -> bytes:
    """Render the pipeline result as a PDF and return the raw bytes."""
    html_content = _build_html(pipeline_result)
    pdf_bytes = HTML(string=html_content).write_pdf()
    logger.info(
        "PDF generated for pipeline_id=%s (%d bytes)",
        pipeline_result.get("pipeline_id"), len(pdf_bytes),
    )
    return pdf_bytes
