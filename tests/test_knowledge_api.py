import json
import unittest
from unittest.mock import patch

import src.main as main


class KnowledgeAPIIntegrationTests(unittest.TestCase):
    def test_answer_hides_citation_markers_but_keeps_reranking(self):
        request = main.KnowledgeChatRequest(
            messages=[main.ChatMessage(role="user", content="猴痘潜伏期多久？")]
        )
        candidate_ids = [
            item.chunk.id
            for item in main.rag_index().search("猴痘潜伏期多久？")[:3]
        ]
        responses = [
            json.dumps({"ids": candidate_ids}, ensure_ascii=False),
            "猴痘潜伏期通常为 5 至 21 天。[K1]",
        ]

        with patch.object(main, "API_KEY", "test-key"), patch.object(
            main, "complete", side_effect=responses
        ) as mocked_complete:
            result = main.knowledge_chat(request)

        self.assertNotIn("[K1]", result["answer"])
        self.assertEqual(result["atlas_disease_ids"], [])
        self.assertEqual(result["retrieval"]["reranker"], "llm-reranker")
        answer_prompt = mocked_complete.call_args_list[-1].args[0][0]["content"]
        self.assertIn("先判断问题复杂度", answer_prompt)
        self.assertIn("简单事实", answer_prompt)
        self.assertIn("**潜伏期：**", answer_prompt)
        self.assertIn("**前驱期（发病早期，约 0—5 天）：**", answer_prompt)
        self.assertIn("只有操作步骤、时间顺序或决策流程确实有先后关系时", answer_prompt)

    def test_rash_answer_returns_matching_atlas_disease(self):
        request = main.KnowledgeChatRequest(
            messages=[main.ChatMessage(role="user", content="猴痘皮疹有什么特点？")]
        )
        candidate_ids = [
            item.chunk.id
            for item in main.rag_index().search("猴痘皮疹有什么特点？")[:3]
        ]
        responses = [
            json.dumps({"ids": candidate_ids}, ensure_ascii=False),
            "猴痘皮疹可经历丘疹、水疱、脓疱和结痂等阶段。",
        ]

        with patch.object(main, "API_KEY", "test-key"), patch.object(
            main, "complete", side_effect=responses
        ):
            result = main.knowledge_chat(request)

        self.assertEqual(result["atlas_disease_ids"], ["mpox"])

    def test_rash_comparison_preserves_disease_mention_order(self):
        result = main.atlas_disease_ids_for_answer(
            "麻疹和风疹的皮疹如何鉴别？",
            "麻疹常见融合性斑丘疹，风疹的皮疹通常较细小。",
        )

        self.assertEqual(result, ["measles", "rubella"])


if __name__ == "__main__":
    unittest.main()
