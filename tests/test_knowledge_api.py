import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

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
            main, "RAG_LLM_RERANK_ENABLED", True
        ), patch.object(
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

    def test_default_path_uses_one_model_call(self):
        request = main.KnowledgeChatRequest(
            messages=[main.ChatMessage(role="user", content="猴痘潜伏期多久？")]
        )

        with patch.object(main, "API_KEY", "test-key"), patch.object(
            main, "RAG_LLM_RERANK_ENABLED", False
        ), patch.object(
            main, "complete", return_value="猴痘潜伏期通常为 5 至 21 天。"
        ) as mocked_complete:
            result = main.knowledge_chat(request)

        self.assertEqual(mocked_complete.call_count, 1)
        self.assertEqual(result["retrieval"]["reranker"], "deterministic-fallback")

    def test_streaming_endpoint_emits_incremental_and_final_events(self):
        client = TestClient(main.app)

        with patch.object(main, "RAG_LLM_RERANK_ENABLED", False), patch.object(
            main,
            "stream_completion",
            return_value=iter(["**潜伏期：** ", "5 至 21 天。"]),
        ):
            response = client.post(
                "/api/chat/knowledge/stream",
                json={"messages": [{"role": "user", "content": "猴痘潜伏期多久？"}]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("content-encoding"), None)
        self.assertIn("event: delta", response.text)
        self.assertIn("event: done", response.text)
        self.assertIn("5 至 21 天", response.text)

    def test_streaming_endpoint_continues_after_length_limit(self):
        client = TestClient(main.app)
        calls = []

        def fake_stream(messages, *, max_tokens, state):
            calls.append((messages, max_tokens))
            state.provider_observed = True
            if len(calls) == 1:
                state.finish_reason = "length"
                yield "**急性发热期：**\n- 急性起病，"
            else:
                state.finish_reason = "stop"
                yield "伴有高热和头痛。"

        with patch.object(main, "RAG_LLM_RERANK_ENABLED", False), patch.object(
            main, "stream_completion", side_effect=fake_stream
        ):
            response = client.post(
                "/api/chat/knowledge/stream",
                json={"messages": [{"role": "user", "content": "登革热的临床表现"}]},
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], main.KNOWLEDGE_MAX_TOKENS)
        self.assertEqual(calls[1][1], main.KNOWLEDGE_CONTINUATION_MAX_TOKENS)
        self.assertIn("上一个回答因输出长度限制被截断", calls[1][0][-1]["content"])
        self.assertIn("伴有高热和头痛", response.text)
        self.assertIn("event: done", response.text)

    def test_empty_stream_falls_back_to_complete_answer(self):
        client = TestClient(main.app)

        with patch.object(main, "RAG_LLM_RERANK_ENABLED", False), patch.object(
            main, "stream_completion", return_value=iter([])
        ), patch.object(
            main, "complete", return_value="登革热常见急性发热、头痛和肌肉关节痛。"
        ) as mocked_complete:
            response = client.post(
                "/api/chat/knowledge/stream",
                json={"messages": [{"role": "user", "content": "登革热的临床表现"}]},
            )

        self.assertEqual(mocked_complete.call_count, 1)
        self.assertIn("event: delta", response.text)
        self.assertIn("event: done", response.text)
        self.assertIn("登革热常见急性发热", response.text)

    def test_empty_stream_never_returns_blank_done_event(self):
        client = TestClient(main.app)

        with patch.object(main, "RAG_LLM_RERANK_ENABLED", False), patch.object(
            main, "stream_completion", return_value=iter([])
        ), patch.object(main, "complete", return_value=""):
            response = client.post(
                "/api/chat/knowledge/stream",
                json={"messages": [{"role": "user", "content": "登革热的临床表现"}]},
            )

        self.assertIn("event: error", response.text)
        self.assertNotIn("event: done", response.text)

    def test_long_conversation_only_sends_recent_bounded_history(self):
        messages = []
        for index in range(7):
            messages.extend(
                [
                    main.ChatMessage(role="user", content=f"第 {index} 轮问题"),
                    main.ChatMessage(role="assistant", content=f"第 {index} 轮回答"),
                ]
            )
        messages.append(main.ChatMessage(role="user", content="最后一个问题"))
        request = main.KnowledgeChatRequest(messages=messages)

        with patch.object(main, "RAG_LLM_RERANK_ENABLED", False):
            _, model_messages, _, _ = main.knowledge_completion(request)

        history = model_messages[1:]
        self.assertLessEqual(len(history), main.KNOWLEDGE_HISTORY_MAX_MESSAGES)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[-1]["content"], "最后一个问题")
        self.assertNotIn("第 0 轮问题", [item["content"] for item in history])

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
