"""Pre-consultation intelligence.

Turns a structured pre-consultation form into a doctor-facing reference used in
the last minute before a consultation:

1. Preconsultation Summary - who the patient is, criticality-first.
2. Family Risk Summary      - hereditary risk, cross-referenced with the
                              patient's own current findings where possible.
3. Probe Checklist          - scored, tagged probing directions telling the
                              doctor where to dig. Concern-mode axes for patients
                              with pressing findings (red_flag_escalation,
                              contradiction_resolution, risk_refinement,
                              treatment_efficacy, diagnostic_clarification,
                              missing_context, medication_adherence,
                              lifestyle_driver); wellness-mode axes for healthy
                              patients (preventive_screening,
                              early_risk_surveillance, baseline_establishment,
                              lifestyle_optimization, goal_alignment). A per-axis
                              importance weight feeds the score internally.

Mental model for the input (v3 pre-consultation form):
    Concern = a patient-declared health concern (e.g. High Blood Pressure), with
              its daily-life impact, duration, trend, symptoms, sources, nested
              family history, and validation answers.
    Cluster = a higher-level health pattern the concerns roll up into (e.g.
              Cardiometabolic Risk), already scored upstream (final_score /
              bucket). The cluster is the unit of criticality; the concerns are
              the supporting detail.
"""

from intelligence_engine.preconsultation.summarize import (
    ChecklistProbe,
    ConcernHypothesis,
    PreconsultationSummaries,
    WellnessHypothesis,
    asummarize_patient,
    summarize_patient,
)
from intelligence_engine.preconsultation.extract_insights import (
    DEFAULT_OCR_CONFIG,
    LEGACY_OCR_CONFIG,
    Citation,
    DocumentInsights,
    ExtractionRunResult,
    Insight,
    OCRConfig,
    SkippedFile,
    SourceIndex,
    aextract_insights,
    aextract_insights_batch,
    extract_insights,
    extract_insights_batch,
)

__all__ = [
    "PreconsultationSummaries",
    "ChecklistProbe",
    "ConcernHypothesis",
    "WellnessHypothesis",
    "summarize_patient",
    "asummarize_patient",
    "Citation",
    "DocumentInsights",
    "ExtractionRunResult",
    "SkippedFile",
    "Insight",
    "SourceIndex",
    "OCRConfig",
    "DEFAULT_OCR_CONFIG",
    "LEGACY_OCR_CONFIG",
    "extract_insights",
    "extract_insights_batch",
    "aextract_insights",
    "aextract_insights_batch",
]
