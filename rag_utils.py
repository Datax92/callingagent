"""
RAG Utilities for Urdu Voicebot
Architecture: Small JSON knowledge base with filtered lookup (not vector search)
"""
import json
import logging
import os
import re
import unicodedata
from typing import Optional

logger = logging.getLogger("voice-agent.rag")

_DEFAULT_KB_FILENAME = "datax_technologies_approved_rag.jsonl"
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_BASE_PATH = os.getenv(
    "RAG_KB_PATH",
    os.path.join(_MODULE_DIR, _DEFAULT_KB_FILENAME),
)

_ARABIC_TO_URDU_MAP = str.maketrans({
    "ي": "ی",   # Arabic Yeh -> Urdu Yeh
    "ك": "ک",   # Arabic Kaf -> Urdu Keheh
    "ه": "ہ",   # Arabic Heh -> Urdu Heh Goal
    "ة": "ہ",   # Teh Marbuta -> Heh Goal
    "ؤ": "و",   # Waw with Hamza -> plain Waw
    "أ": "ا",   # Alef with Hamza above -> plain Alef
    "إ": "ا",   # Alef with Hamza below -> plain Alef
    "آ": "ا",   # Alef Madda -> plain Alef
    "ئ": "ی",   # Yeh with Hamza -> Yeh
})

# Arabic combining diacritics
_DIACRITICS_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0670]"
)
# Urdu/Arabic + common Latin punctuation
_PUNCT_RE = re.compile(r"[۔،؟!٫٬»«\"'.,?!:;()\[\]{}\-–—]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_urdu(text: str) -> str:
    """Unify Unicode letter variants, strip diacritics/punctuation, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _DIACRITICS_RE.sub("", text)
    text = text.translate(_ARABIC_TO_URDU_MAP)
    text = _PUNCT_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text.lower()


class RAGUtils:
    """
    RAG utility for filtered keyword-based lookup.
    Architecture requirement: Filtered lookup (<500 tokens), not full-file injection.
    """

    def __init__(self, knowledge_base_path: str | None = None):
        self.knowledge_base_path = knowledge_base_path or KNOWLEDGE_BASE_PATH
        self.knowledge_base = self._load_knowledge_base()

    def _load_knowledge_base(self) -> list[dict]:
        """Load the knowledge base from a JSONL file."""
        resolved_path = os.path.abspath(self.knowledge_base_path)
        try:
            if not os.path.exists(self.knowledge_base_path):
                logger.error(
                    f"RAG knowledge base file NOT FOUND at '{resolved_path}'. "
                    f"All RAG lookups will return nothing until this file exists there."
                )
                return []

            data = []
            with open(self.knowledge_base_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipping malformed JSON on line {line_num} of '{resolved_path}': {e}")

            if not data:
                logger.warning(f"Knowledge base at '{resolved_path}' exists but has 0 usable entries.")
            else:
                logger.info(f"Loaded RAG knowledge base with {len(data)} entries from '{resolved_path}'")
            return data
        except Exception as e:
            logger.error(f"Error loading knowledge base from '{resolved_path}': {e}")
            return []

    def filtered_lookup(self, query: str) -> Optional[str]:
        """
        Perform a filtered keyword-based lookup.
        Args:
            query: User's spoken text or transcript for lookup
        Returns:
            Relevant knowledge chunk as text, or None if no match
        """
        if not self.knowledge_base:
            logger.warning("RAG lookup skipped — knowledge base is empty.")
            return None

        query_normalized = _normalize_urdu(query)
        if not query_normalized:
            return None

        # --------------------------------------------------------------
        # URDU KEYWORD SUBSTRING MATCHING:
        # Check if any phrase in 'ur_keywords' is a substring of the query string.
        # This resolves STT word-splitting and slight variation issues.
        # --------------------------------------------------------------
        best_kw_entry = None
        best_kw_score = 0
        kw_debug = []

        for entry in self.knowledge_base:
            ur_keywords = entry.get('ur_keywords')
            if not ur_keywords:
                continue
            content = entry.get('content', '') or entry.get('text', '') or entry.get('description', '')
            if not content:
                continue

            score = 0
            for phrase in ur_keywords:
                phrase_norm = _normalize_urdu(phrase)
                # Substring containment check
                if phrase_norm and phrase_norm in query_normalized:
                    # Give higher score to longer phrases (more words matched)
                    score += len(phrase_norm.split())

            if score > 0:
                kw_debug.append((score, content[:60]))

            if score > best_kw_score:
                best_kw_score = score
                best_kw_entry = content

        if best_kw_entry:
            words = best_kw_entry.split()
            result = " ".join(words[:500]) if len(words) > 500 else best_kw_entry
            logger.info(f"RAG lookup matched entry via ur_keywords (score={best_kw_score}), {len(result.split())} words")
            return result

        # --------------------------------------------------------------
        # Fallback: Generic word-overlap for non-keyword / raw text entries
        # --------------------------------------------------------------
        query_words = set(query_normalized.split())
        best_entry = None
        best_score = -1
        best_candidates_debug = []

        for entry in self.knowledge_base:
            content = entry.get('content', '') or entry.get('text', '') or entry.get('description', '')
            if not content:
                continue

            content_words = set(_normalize_urdu(content).split())
            score = len(content_words & query_words)

            if score > 0:
                best_candidates_debug.append((score, content[:60]))

            if score > best_score:
                best_score = score
                best_entry = content

        if best_score >= 2 and best_entry:
            words = best_entry.split()
            result = " ".join(words[:500]) if len(words) > 500 else best_entry
            logger.info(f"RAG lookup matched entry with {best_score} overlap keywords, {len(result.split())} words")
            return result
        else:
            best_candidates_debug.sort(key=lambda x: x[0], reverse=True)
            if best_candidates_debug:
                logger.info(
                    f"No RAG match above threshold (best_score={best_score}) for query: '{query[:80]}'. "
                    f"Closest candidates: {best_candidates_debug[:3]}"
                )
            else:
                logger.info(f"No RAG match above threshold (best_score={best_score}) for query: '{query[:80]}'")
            return None