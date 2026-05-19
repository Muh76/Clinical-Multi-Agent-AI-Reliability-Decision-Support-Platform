from __future__ import annotations

import math
import re
from collections import Counter

from clinical_ai_retrieval.schemas import EvidenceDocument, MetadataFilter, RetrievalResult
from clinical_ai_retrieval.scoring import attach_reliability_scores


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]*")


class BM25Retriever:
    def __init__(self, *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._documents: list[EvidenceDocument] = []
        self._term_frequencies: list[Counter[str]] = []
        self._document_frequency: Counter[str] = Counter()
        self._document_lengths: list[int] = []
        self._average_document_length = 0.0

    def index_documents(self, documents: list[EvidenceDocument]) -> None:
        self._documents = documents
        self._term_frequencies = []
        self._document_frequency = Counter()
        self._document_lengths = []
        for document in documents:
            terms = tokenize(document.text)
            term_frequency = Counter(terms)
            self._term_frequencies.append(term_frequency)
            self._document_lengths.append(len(terms))
            self._document_frequency.update(term_frequency.keys())
        if self._document_lengths:
            self._average_document_length = (
                sum(self._document_lengths) / len(self._document_lengths)
            )

    async def retrieve(
        self,
        *,
        query: str,
        limit: int,
        filters: MetadataFilter,
    ) -> list[RetrievalResult]:
        query_terms = tokenize(query)
        scored_results: list[RetrievalResult] = []
        for index, document in enumerate(self._documents):
            if not metadata_matches(document, filters):
                continue
            score = self._score(query_terms, index)
            if score <= 0:
                continue
            normalized_score = score / (score + 1.0)
            scored_results.append(
                RetrievalResult(
                    chunk_id=f"{document.document_id}:bm25",
                    document_id=document.document_id,
                    score=normalized_score,
                    text=document.text,
                    metadata=document.metadata,
                    lexical_score=normalized_score,
                )
            )
        ranked = sorted(scored_results, key=lambda result: result.score, reverse=True)
        return attach_reliability_scores(ranked[:limit])

    def _score(self, query_terms: list[str], document_index: int) -> float:
        score = 0.0
        term_frequency = self._term_frequencies[document_index]
        document_length = self._document_lengths[document_index]
        for term in query_terms:
            frequency = term_frequency.get(term, 0)
            if frequency == 0:
                continue
            idf = self._idf(term)
            numerator = frequency * (self.k1 + 1.0)
            denominator = frequency + self.k1 * (
                1.0 - self.b + self.b * document_length / self._average_document_length
            )
            score += idf * numerator / denominator
        return score

    def _idf(self, term: str) -> float:
        document_count = len(self._documents)
        matching_count = self._document_frequency.get(term, 0)
        return math.log(1.0 + (document_count - matching_count + 0.5) / (matching_count + 0.5))


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def metadata_matches(document: EvidenceDocument, filters: MetadataFilter) -> bool:
    metadata = document.metadata
    if filters.source_types and metadata.source_type not in filters.source_types:
        return False
    if filters.clinical_domains:
        domains = set(metadata.clinical_domains)
        if not domains.intersection(filters.clinical_domains):
            return False
    for field_name in (
        "patient_id",
        "encounter_id",
        "guideline_org",
        "imaging_modality",
        "body_part",
        "evidence_level",
    ):
        filter_value = getattr(filters, field_name)
        if filter_value is not None and getattr(metadata, field_name) != filter_value:
            return False
    if filters.publication_year_min is not None:
        if (
            metadata.publication_year is None
            or metadata.publication_year < filters.publication_year_min
        ):
            return False
    if filters.publication_year_max is not None:
        if (
            metadata.publication_year is None
            or metadata.publication_year > filters.publication_year_max
        ):
            return False
    return True
