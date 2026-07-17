"""Cite-then-verify unit tests (LLM mocked at the client boundary)."""

from app.services.qa.answer import cited_chunk_ids
from app.services.qa.intent import keyword_intent
from app.services.qa.verify import (
    NUMERIC_TOKEN_RE,
    split_claims,
    strip_unsupported,
    verify_claims,
)


class FakeLLM:
    """LLMClient stand-in: no network, configurable answers."""

    def __init__(self, json_response=None, configured=True):
        self.json_response = json_response
        self._configured = configured
        self.models_used = set()

    @property
    def is_configured(self):
        return self._configured

    def chat_json(self, messages, model=None, temperature=0.0):
        return self.json_response

    def chat_text(self, messages, model=None, **kwargs):
        return None


CHUNKS = {
    7: {
        "chunk_id": 7,
        "content": (
            "City Council — 2026-07-01\nItem 4.a: Small cell franchise "
            "agreement approved with a fee of $2,500,000 per year. "
            "Vote: 7-2 in favor."
        ),
    },
    9: {
        "chunk_id": 9,
        "content": "Item 5.b: Park maintenance contract for Mohawk Park.",
    },
}


class TestCitationContract:
    def test_cited_chunk_ids(self):
        answer = "The fee is $2,500,000 per year [c:7]. It passed 7-2 [c:7]."
        assert cited_chunk_ids(answer) == [7, 7]

    def test_split_claims_attaches_ids(self):
        answer = "The fee is $2,500,000 [c:7]. Parks were discussed [c:9]."
        claims = split_claims(answer)
        assert claims[0][1] == [7]
        assert claims[1][1] == [9]


class TestNumericVerification:
    def test_supported_numeric_claim(self):
        answer = "The franchise fee is $2,500,000 per year [c:7]."
        claims = verify_claims(answer, CHUNKS, FakeLLM(configured=False))
        assert claims[0].supported

    def test_fabricated_figure_is_stripped(self):
        answer = "The franchise fee is $9,999,999 per year [c:7]."
        claims = verify_claims(answer, CHUNKS, FakeLLM(configured=False))
        assert not claims[0].supported
        assert "9,999,999" in claims[0].reason
        rebuilt, dropped = strip_unsupported(claims)
        assert rebuilt == ""
        assert len(dropped) == 1

    def test_vote_tally_checked(self):
        good = verify_claims("It passed 7-2 [c:7].", CHUNKS, FakeLLM(configured=False))
        bad = verify_claims("It passed 8-1 [c:7].", CHUNKS, FakeLLM(configured=False))
        assert good[0].supported
        assert not bad[0].supported

    def test_uncited_factual_claim_unsupported(self):
        answer = (
            "The council allocated $5,000,000 for road repairs across "
            "all nine districts without any recorded opposition."
        )
        claims = verify_claims(answer, CHUNKS, FakeLLM(configured=False))
        assert not claims[0].supported
        assert claims[0].reason == "no citation"

    def test_numeric_regex_forms(self):
        text = "$2,500,000 and 1,234 people and 45% and 7-2"
        tokens = NUMERIC_TOKEN_RE.findall(text)
        assert "$2,500,000" in tokens
        assert "45%" in tokens
        assert "7-2" in tokens


class TestNLIVerification:
    def test_nli_rejection_marks_unsupported(self):
        answer = "The park contract covers Mohawk Park [c:9]."
        llm = FakeLLM(json_response={"supported": {"0": False}})
        claims = verify_claims(answer, CHUNKS, llm)
        assert not claims[0].supported
        assert claims[0].reason == "not entailed by cited source"

    def test_nli_acceptance(self):
        answer = "The park contract covers Mohawk Park [c:9]."
        llm = FakeLLM(json_response={"supported": {"0": True}})
        claims = verify_claims(answer, CHUNKS, llm)
        assert claims[0].supported


class TestIntent:
    def test_keyword_intents(self):
        assert keyword_intent("Who represents me at 175 E 2nd St?") == (
            "district_lookup"
        )
        assert keyword_intent("How much budget goes to parks?") == "budget_figure"
        assert keyword_intent("When did the council vote on this?") == (
            "meeting_lookup"
        )
        assert keyword_intent("Tell me about housing policy") == "topic_question"
