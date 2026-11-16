"""PDF -> ExtractionResult: deterministic MH parser first, AI fallback when the parser is not enough."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.domain import DteRecord, ExtractionMethod, ExtractionResult, Issue, IssueSeverity

from .ai import AiExtractor
from .layout import PdfReadError, read_pdf_pages
from .mh_parser import ParsedDocument, parse_pages
from .validation import validate_record

logger = logging.getLogger(__name__)


@dataclass
class _Candidate:
    method: ExtractionMethod
    documents: list[ParsedDocument]
    failure: str | None = None
    raw_text: str | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def records(self) -> list[DteRecord]:
        return [d.record for d in self.documents]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == IssueSeverity.ERROR)


def _with_validation(documents: list[ParsedDocument]) -> list[Issue]:
    """Issues of every document (parse issues + validate_record), prefixed when the PDF has several."""
    issues: list[Issue] = []
    many = len(documents) > 1
    for index, document in enumerate(documents, start=1):
        seen: set[tuple[str, str | None]] = set()
        doc_issues: list[Issue] = []
        for issue in [*document.issues, *validate_record(document.record)]:
            key = (issue.code, issue.field)
            if key in seen:
                continue
            seen.add(key)
            doc_issues.append(issue)
        for issue in doc_issues:
            if many:
                ref = document.record.codigo_generacion or f"#{index}"
                issue = issue.model_copy(update={"message": f"Documento {index} ({ref}): {issue.message}"})
            issues.append(issue)
    return issues


def _run_parser(pdf_bytes: bytes) -> _Candidate:
    try:
        pages = read_pdf_pages(pdf_bytes)
    except PdfReadError as exc:
        logger.info("PDF could not be opened: %s", exc)
        return _Candidate(ExtractionMethod.PARSER, [], failure="el archivo no es un PDF válido o está dañado")
    outcome = parse_pages(pages)
    candidate = _Candidate(
        ExtractionMethod.PARSER, outcome.documents, failure=outcome.failure, raw_text=outcome.raw_text or None
    )
    candidate.issues = _with_validation(candidate.documents)
    return candidate


def _first_error(candidate: _Candidate) -> str:
    if candidate.failure:
        return candidate.failure
    for issue in candidate.issues:
        if issue.severity == IssueSeverity.ERROR:
            return issue.message.rstrip(".")
    return "la lectura automática no fue concluyente"


def _unreadable(reason: str) -> Issue:
    return Issue(
        code="pdf_unreadable", severity=IssueSeverity.ERROR, message=f"No se pudo leer el PDF: {reason}."
    )


def _parser_result(parser: _Candidate, extra: list[Issue]) -> ExtractionResult:
    issues = list(parser.issues)
    if not parser.documents:
        issues.insert(0, _unreadable(parser.failure or "no se encontraron documentos"))
    issues.extend(extra)
    return ExtractionResult(
        method=ExtractionMethod.PARSER, records=parser.records, issues=issues, raw_text=parser.raw_text
    )


def extract_pdf(pdf_bytes: bytes, *, ai: AiExtractor | None) -> ExtractionResult:
    """Read every DTE in a PDF. Never raises for bad input or AI failures; problems become Issues."""
    parser = _run_parser(pdf_bytes)
    if parser.documents and parser.error_count == 0:
        return _parser_result(parser, [])
    if ai is None:
        return _parser_result(parser, [])

    reason = _first_error(parser)
    try:
        ai_records = ai.extract(pdf_bytes)
    except Exception as exc:  # the extractor must never break extraction, whatever it raises
        logger.warning("AI extraction failed: %s", exc)
        detail = str(exc) or type(exc).__name__
        return _parser_result(
            parser,
            [
                Issue(
                    code="ai_extraction_failed",
                    severity=IssueSeverity.WARNING,
                    message=f"Se intentó leer el documento con IA y falló: {detail}",
                )
            ],
        )

    if not ai_records:
        return _parser_result(
            parser,
            [
                Issue(
                    code="ai_extraction_failed",
                    severity=IssueSeverity.WARNING,
                    message="Se intentó leer el documento con IA pero no encontró ningún DTE.",
                )
            ],
        )

    ai_candidate = _Candidate(ExtractionMethod.AI, [ParsedDocument(record=r) for r in ai_records])
    ai_candidate.issues = _with_validation(ai_candidate.documents)

    if parser.documents and parser.error_count <= ai_candidate.error_count:
        return _parser_result(
            parser,
            [
                Issue(
                    code="ai_result_discarded",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Se intentó leer el documento con IA ({ai_candidate.error_count} errores) pero se "
                        f"conservó la lectura automática ({parser.error_count} errores)."
                    ),
                )
            ],
        )

    note = Issue(
        code="ai_extraction_used",
        severity=IssueSeverity.WARNING,
        message=f"El documento se leyó con IA porque {reason[:1].lower()}{reason[1:]}. Revise los datos.",
    )
    return ExtractionResult(
        method=ExtractionMethod.AI,
        records=ai_candidate.records,
        issues=[note, *ai_candidate.issues],
        raw_text=parser.raw_text,
    )
