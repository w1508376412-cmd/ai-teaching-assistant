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
        self.assertEqual(result["retrieval"]["reranker"], "llm-reranker")
        answer_prompt = mocked_complete.call_args_list[-1].args[0][0]["content"]
        self.assertIn("先判断问题复杂度", answer_prompt)
        self.assertIn("简单事实", answer_prompt)
        self.assertIn("### 一、标题", answer_prompt)


if __name__ == "__main__":
    unittest.main()
