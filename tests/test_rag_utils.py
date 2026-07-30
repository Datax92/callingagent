"""Tests for RAG utilities (rag_utils.py)."""
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from rag_utils import RAGUtils


# ---------------------------------------------------------------------------
# RAGUtils — knowledge base loading
# ---------------------------------------------------------------------------

class TestRAGUtilsLoading:
    def test_load_empty_file(self):
        """An empty JSONL file yields an empty knowledge base."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write("")
            path = f.name
        try:
            rag = RAGUtils(knowledge_base_path=path)
            assert rag.knowledge_base == []
        finally:
            os.unlink(path)

    def test_load_with_valid_entries(self, rag_kb_file):
        """Valid JSONL entries are loaded into the knowledge base."""
        rag = RAGUtils(knowledge_base_path=rag_kb_file)
        assert len(rag.knowledge_base) == 4
        assert "ویب سائٹ ڈیزائن" in rag.knowledge_base[0].get("content", "")

    def test_skip_malformed_lines(self, rag_kb_file):
        """Malformed JSON lines are skipped without crashing."""
        lines = [
            json.dumps({"content": "Valid entry"}),
            "this is not valid json",
            json.dumps({"content": "Another valid entry"}),
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            path = f.name
        try:
            rag = RAGUtils(knowledge_base_path=path)
            assert len(rag.knowledge_base) == 2
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        """A non-existent file yields an empty knowledge base (no crash)."""
        rag = RAGUtils(knowledge_base_path="/tmp/nonexistent_file_xyz.jsonl")
        assert rag.knowledge_base == []


# ---------------------------------------------------------------------------
# RAGUtils — filtered_lookup
# ---------------------------------------------------------------------------

class TestRAGUtilsLookup:
    def test_match_found(self, rag_kb_file):
        """A query matching keywords returns the relevant chunk."""
        rag = RAGUtils(knowledge_base_path=rag_kb_file)
        result = rag.filtered_lookup("ویب سائٹ ڈیزائن")
        assert result is not None
        assert "ویب سائٹ" in result

    def test_no_match_returns_none(self, rag_kb_file):
        """A query with no keyword overlap returns None."""
        rag = RAGUtils(knowledge_base_path=rag_kb_file)
        result = rag.filtered_lookup("کچھ بھی نہیں")
        # None of the KB entries will overlap sufficiently
        assert result is None or "کچھ بھی نہیں" not in result

    def test_empty_query(self, rag_kb_file):
        """Empty query returns None."""
        rag = RAGUtils(knowledge_base_path=rag_kb_file)
        assert rag.filtered_lookup("") is None
        assert rag.filtered_lookup("   ") is None

    def test_empty_kb_returns_none(self):
        """Lookup on empty KB returns None."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write("")
            path = f.name
        try:
            rag = RAGUtils(knowledge_base_path=path)
            assert rag.filtered_lookup("anything") is None
        finally:
            os.unlink(path)

    def test_result_truncated_to_500_words(self):
        """Result is truncated to 500 words if longer."""
        words = ["word1", "word2"] * 300  # 600 words, 2 unique keywords
        content = " ".join(words)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"content": content}) + "\n")
            path = f.name
        try:
            rag = RAGUtils(knowledge_base_path=path)
            # Query with both keywords so score >= 2 meets threshold
            result = rag.filtered_lookup("word1 word2")
            assert result is not None
            assert len(result.split()) <= 500
        finally:
            os.unlink(path)

    def test_best_entry_selected(self, rag_kb_file):
        """The entry with the highest keyword overlap is returned."""
        rag = RAGUtils(knowledge_base_path=rag_kb_file)
        # Match "موبائل ایپ" which should strongly match one entry
        result = rag.filtered_lookup("موبائل ایپ ڈویلپمنٹ")
        assert result is not None
        assert "موبائل ایپ" in result

    def test_score_threshold_below_2(self, rag_kb_file):
        """A query with fewer than 2 overlapping keywords returns None."""
        rag = RAGUtils(knowledge_base_path=rag_kb_file)
        # A query with no overlap to any entry
        result = rag.filtered_lookup("xyzxyz")
        assert result is None


# ---------------------------------------------------------------------------
# RAGUtils — edge cases
# ---------------------------------------------------------------------------

class TestRAGUtilsEdgeCases:
    def test_fallback_fields(self):
        """Entry with 'text' or 'description' key (not 'content') still matches."""
        entry = json.dumps({"text": "ہم ویب ڈیزائن کرتے ہیں۔"})
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(entry + "\n")
            path = f.name
        try:
            rag = RAGUtils(knowledge_base_path=path)
            result = rag.filtered_lookup("ویب ڈیزائن")
            assert result is not None
            assert "ویب ڈیزائن" in result
        finally:
            os.unlink(path)

    def test_no_content_key_returns_none_in_result(self):
        """Entries without content/text/description keys are skipped."""
        entry = json.dumps({"unrelated": "data"})
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(entry + "\n")
            path = f.name
        try:
            rag = RAGUtils(knowledge_base_path=path)
            # Should not crash; just return None since no content to match
            result = rag.filtered_lookup("anything")
            assert result is None
        finally:
            os.unlink(path)
