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

# --------------------------------------------------------------------------
# FIX: The knowledge base path used to be a bare relative filename, which is
# resolved against the process's current working directory — NOT the
# directory this script lives in. If the worker is launched from anywhere
# else (systemd, Docker, a process manager, `cd`'d into a different folder),
# the file silently fails to be found and every RAG lookup returns None
# forever, with no error surfaced anywhere.
#
# Fix: resolve the default path relative to this file's own directory, and
# allow a full override via the RAG_KB_PATH environment variable so deployment
# configs can point at the real location explicitly.
# --------------------------------------------------------------------------
_DEFAULT_KB_FILENAME = "datax_technologies_approved_rag.jsonl"
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_BASE_PATH = os.getenv(
    "RAG_KB_PATH",
    os.path.join(_MODULE_DIR, _DEFAULT_KB_FILENAME),
)

# --------------------------------------------------------------------------
# FIX: filtered_lookup was comparing raw whitespace-split words with `==`
# (via set intersection), which fails silently whenever the KB text and the
# live STT transcript use different-but-visually-identical Unicode forms for
# the same Urdu letter — extremely common when a KB is typed/copy-pasted from
# an Arabic-script source while the STT engine emits standard Urdu forms.
# e.g. Arabic Yeh "ي" (U+064A) vs Urdu Yeh "ی" (U+06CC), Arabic Kaf "ك"
# (U+0643) vs Urdu Keheh "ک" (U+06A9), Arabic Heh "ه" vs Urdu Heh Goal "ہ"
# (U+06C1), plus optional Arabic diacritics (zabar/zer/pesh) that sometimes
# ride along in KB text but never appear in transcripts. On top of that,
# Deepgram's auto-punctuation attaches "؟"/"۔"/"،" directly to the last word
# of an utterance ("ہیں؟"), which never matches an unpunctuated KB word
# ("ہیں"). Any one of these silently zeroes out every overlap score.
#
# Fix: normalize both KB content and the live query the same way before
# splitting into words — unify letter variants, strip diacritics, and strip
# punctuation — so identical-looking words actually compare equal.
# --------------------------------------------------------------------------
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

# Arabic combining diacritics (zabar, zer, pesh, tanwin, shadda, sukun, etc.)
_DIACRITICS_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0670]"
)
# Urdu/Arabic + common Latin punctuation that can get glued onto words
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
                # FIX: was a `warning` at INFO-suppressible severity buried among
                # startup noise; bumped to `error` with an explicit, actionable
                # message since this is a total-failure condition, not a minor one.
                logger.error(
                    f"RAG knowledge base file NOT FOUND at '{resolved_path}'. "
                    f"All RAG lookups will return nothing until this file exists there, "
                    f"or RAG_KB_PATH / knowledge_base_path is set to the correct location."
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
                        # FIX: previously one bad line would raise and wipe out
                        # the entire KB (caught by the outer except -> []).
                        # Now we skip just the bad line and keep the rest.
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

        Architecture: Returns only the most relevant chunk (<500 tokens).
        Not a vector search - simple keyword matching works for small KB.

        Args:
            query: User's spoken text or transcript for lookup

        Returns:
            Relevant knowledge chunk as text, or None if no match
        """
        if not self.knowledge_base:
            logger.warning("RAG lookup skipped — knowledge base is empty (see startup error above).")
            return None

        query_normalized = _normalize_urdu(query)
        if not query_normalized:
            return None
        query_words = set(query_normalized.split())

        # --------------------------------------------------------------
        # FIX: the KB's `content` field is written in English (compliance /
        # reference text), while every live query is Urdu speech. A literal
        # word-overlap match between the two languages will always score 0,
        # no matter how well-normalized the text is — there's no shared
        # vocabulary to find. Entries can now carry a curated `ur_keywords`
        # list (short Urdu trigger phrases a caller would actually say,
        # e.g. "ویب سائٹ بنوانی", "کتنے پیسے لگیں گے") which we match
        # against first. `content` stays in English — that's fine, since
        # the LLM reads it for grounding and answers in Urdu itself; only
        # the *retrieval* step needed an Urdu-side key.
        # A phrase counts as matched if every one of its words appears in
        # the query, so multi-word keywords score higher than incidental
        # single-word overlaps, and one clean phrase match is enough to
        # surface an entry (unlike the generic 2-word threshold below,
        # which needs a broader coincidental overlap to be meaningful).
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
                phrase_words = set(_normalize_urdu(phrase).split())
                if phrase_words and phrase_words.issubset(query_words):
                    score += len(phrase_words)

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
        # Fallback: generic content word-overlap, for any entry that has
        # no ur_keywords yet (e.g. newly added English-only content).
        # --------------------------------------------------------------
        best_entry = None
        best_score = -1
        best_candidates_debug = []  # top few (score, content_snippet) for troubleshooting

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

        # Threshold for meaningful match (at least 2 overlapping keywords)
        if best_score >= 2 and best_entry:
            words = best_entry.split()
            if len(words) > 500:
                result = " ".join(words[:500])
            else:
                result = best_entry

            logger.info(f"RAG lookup matched entry with {best_score} keywords, {len(result.split())} words")
            return result
        else:
            # FIX: now logs the query itself so you can tell in the logs
            # whether it's a genuine no-match vs. an empty/broken KB. Also
            # logs the closest few candidates (even below threshold) so a
            # near-miss due to normalization/threshold tuning is visible
            # instead of just "no match".
            best_candidates_debug.sort(key=lambda x: x[0], reverse=True)
            if best_candidates_debug:
                logger.info(
                    f"No RAG match above threshold (best_score={best_score}) for query: '{query[:80]}'. "
                    f"Closest candidates: {best_candidates_debug[:3]}"
                )
            else:
                logger.info(f"No RAG match above threshold (best_score={best_score}) for query: '{query[:80]}'")
            return None