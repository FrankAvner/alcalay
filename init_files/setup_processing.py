from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProcessingResult:
    success: bool
    component: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "component": self.component,
            "message": self.message,
        }


def validate_processing(
    configuration: dict[str, Any],
) -> list[ProcessingResult]:
    results: list[ProcessingResult] = []

    processing = configuration.get(
        "processing",
        {},
    )

    components = {
        "text_extraction": "Text extraction",
        "metadata_extraction": "Metadata extraction",
        "classification": "Document classification",
        "keywords": "Keyword extraction",
        "thesaurus": "Thesaurus / cross-reference",
    }

    for key, description in components.items():
        enabled = bool(
            processing.get(
                key,
                False,
            )
        )

        results.append(
            ProcessingResult(
                success=True,
                component=key,
                message=(
                    f"{description}: "
                    f"{'enabled' if enabled else 'disabled'}."
                ),
            )
        )

    return results


def validate_ocr(
    configuration: dict[str, Any],
) -> ProcessingResult:
    ocr = configuration.get(
        "ocr",
        {},
    )

    enabled = bool(
        ocr.get(
            "enabled",
            True,
        )
    )

    language = ocr.get(
        "language",
        "heb+eng",
    )

    automatic = bool(
        ocr.get(
            "automatic",
            True,
        )
    )

    if not enabled:
        return ProcessingResult(
            success=True,
            component="ocr",
            message="OCR is disabled.",
        )

    if not language:
        return ProcessingResult(
            success=False,
            component="ocr",
            message="OCR language is missing.",
        )

    return ProcessingResult(
        success=True,
        component="ocr",
        message=(
            f"OCR enabled; language={language}; "
            f"automatic={automatic}."
        ),
    )


def validate_ai_ml(
    configuration: dict[str, Any],
) -> list[ProcessingResult]:
    results: list[ProcessingResult] = []

    ai_ml = configuration.get(
        "ai_ml",
        {},
    )

    enabled = bool(
        ai_ml.get(
            "enabled",
            True,
        )
    )

    results.append(
        ProcessingResult(
            success=True,
            component="ai_ml",
            message=(
                f"AI/ML processing is "
                f"{'enabled' if enabled else 'disabled'}."
            ),
        )
    )

    if not enabled:
        return results

    components = {
        "semantic": "Semantic understanding",
        "classification": "AI classification",
        "similarity": "Similarity analysis",
    }

    for key, description in components.items():
        component_enabled = bool(
            ai_ml.get(
                key,
                False,
            )
        )

        results.append(
            ProcessingResult(
                success=True,
                component=f"ai_ml.{key}",
                message=(
                    f"{description}: "
                    f"{'enabled' if component_enabled else 'disabled'}."
                ),
            )
        )

    return results


def validate_search(
    configuration: dict[str, Any],
) -> list[ProcessingResult]:
    results: list[ProcessingResult] = []

    search = configuration.get(
        "search",
        {},
    )

    components = {
        "full_text": "Full-text search",
        "metadata": "Metadata search",
        "semantic": "Semantic search",
        "boolean": "Boolean search",
        "reindex_changed_documents": (
            "Reindex changed documents"
        ),
    }

    for key, description in components.items():
        enabled = bool(
            search.get(
                key,
                False,
            )
        )

        results.append(
            ProcessingResult(
                success=True,
                component=f"search.{key}",
                message=(
                    f"{description}: "
                    f"{'enabled' if enabled else 'disabled'}."
                ),
            )
        )

    return results


def validate_processing_configuration(
    configuration: dict[str, Any],
) -> list[ProcessingResult]:
    """
    Validate the complete Alcalay processing stack.

    This module does NOT:
        - execute OCR
        - load AI models
        - process documents
        - create embeddings
        - build search indexes
    """

    results: list[ProcessingResult] = []

    results.extend(
        validate_processing(
            configuration
        )
    )

    results.append(
        validate_ocr(
            configuration
        )
    )

    results.extend(
        validate_ai_ml(
            configuration
        )
    )

    results.extend(
        validate_search(
            configuration
        )
    )

    return results


def validate_processing_dict(
    configuration: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        result.to_dict()
        for result in validate_processing_configuration(
            configuration
        )
    ]


if __name__ == "__main__":
    print("Alcalay Processing Setup Check")
    print("=" * 60)
    print(
        "This module validates processing configuration only."
    )
    print(
        "No OCR, AI/ML, or indexing is executed."
    )