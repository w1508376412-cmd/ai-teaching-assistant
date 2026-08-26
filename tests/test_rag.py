from pathlib import Path
import unittest

from src.rag import StructuredRAG, build_context


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "rag_data" / "chunks.jsonl"


class StructuredRAGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rag = StructuredRAG(CHUNKS)

    def test_corpus_statistics(self):
        stats = self.rag.stats()
        self.assertEqual(stats["chunks"], 267)
        self.assertEqual(stats["diseases"], 33)
        self.assertEqual(stats["documents"], 70)
        self.assertEqual(stats["sources"], 20)

    def test_mpox_query_returns_mpox_evidence(self):
        results = self.rag.search("猴痘潜伏期和皮疹演变有什么特点？")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].chunk.disease, "猴痘")

    def test_conjunctivitis_query_returns_matching_disease(self):
        results = self.rag.search("急性出血性结膜炎如何传播和隔离？")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].chunk.disease, "急性出血性结膜炎")

    def test_context_contains_verifiable_citation_metadata(self):
        results = self.rag.search("登革热的诊断和防控措施")
        context, citations = build_context(results, max_chunks=3)
        self.assertIn("[K1]", context)
        self.assertGreater(len(citations), 0)
        self.assertTrue(citations[0]["source"].startswith(("http://", "https://")))
        self.assertIn("chunk_id", citations[0])


if __name__ == "__main__":
    unittest.main()
