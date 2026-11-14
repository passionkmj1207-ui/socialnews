import json
import tempfile
import unittest
from pathlib import Path

from keyword_maker.config import Config
from keyword_maker.ideas import build_idea, detect_event
from keyword_maker.models import Article, Candidate
from keyword_maker.output import write_all
from keyword_maker.pipeline import run
from keyword_maker.scoring import _norm, score_candidates
from keyword_maker.sources.demo import DemoSources


def cand(ticker="XYZ", titles=(), change=0.0, **kw):
    c = Candidate(ticker=ticker, name_en="Xyz", name_kr="엑스와이지", price_change_pct=change, **kw)
    c.articles = [Article(title=t, source=f"s{i}") for i, t in enumerate(titles)]
    return c


class ScoringTests(unittest.TestCase):
    def test_norm_range_and_ties(self):
        self.assertEqual(_norm([5, 5, 5]), [0.0, 0.0, 0.0])
        n = _norm([1, 2, 3])
        self.assertEqual((n[0], n[1], n[2]), (0.0, 0.5, 1.0))

    def test_hotter_candidate_scores_higher(self):
        hot = cand("HOT", ["a", "b", "c", "d"], change=9, volume_ratio=3.0)
        cold = cand("COLD", ["a"], change=0.2, volume_ratio=0.9)
        score_candidates([hot, cold], Config(), deep=False)
        self.assertGreater(hot.score, cold.score)
        self.assertTrue(0 <= cold.score <= hot.score <= 100)


class EventTests(unittest.TestCase):
    def test_earnings(self):
        self.assertEqual(detect_event(cand(titles=["Xyz earnings beat on cloud growth"])), "earnings")

    def test_miss_without_estimates_is_not_earnings(self):
        self.assertNotEqual(detect_event(cand(titles=["Xyz shares plunge after delivery miss"], change=-6)), "earnings")

    def test_miss_estimates_is_earnings(self):
        self.assertEqual(detect_event(cand(titles=["Xyz misses estimates, cuts outlook"])), "earnings")

    def test_big_move_becomes_primary_for_contract(self):
        i = build_idea(cand(titles=["Xyz wins government contract"], change=8))
        self.assertIn("급등", i.keyword)
        self.assertTrue(any("계약" in k for k in i.alt_keywords))

    def test_general_fallback(self):
        self.assertEqual(build_idea(cand(titles=[])).keyword, "엑스와이지 주가 전망")


class PipelineTests(unittest.TestCase):
    def test_demo_end_to_end(self):
        r = run(DemoSources(), Config(), demo=True, today="2026-01-01")
        self.assertTrue(r.demo)
        self.assertEqual(len(r.stock_ideas), 15)
        self.assertEqual(len(r.macro_ideas), 10)
        scores = [x.score for x in r.stock_ideas]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(x.keyword for x in r.stock_ideas + r.macro_ideas))

    def test_outputs_written_and_demo_marked(self):
        r = run(DemoSources(), Config(), demo=True, today="2026-01-01")
        with tempfile.TemporaryDirectory() as t:
            d = write_all(r, Path(t))
            self.assertTrue(d.name.startswith("demo_"))
            for f in ("keywords.csv", "keywords.md", "keywords.html", "workflow_input.json"):
                self.assertTrue((d / f).exists(), f)
            data = json.loads((d / "workflow_input.json").read_text(encoding="utf-8"))
            self.assertTrue(data["demo"])
            self.assertEqual(len(data["items"]), 25)
            self.assertIn("DEMO", (d / "keywords.md").read_text(encoding="utf-8"))
            self.assertIn("DEMO", (d / "keywords.html").read_text(encoding="utf-8"))

    def test_live_sources_degrade_gracefully_without_network(self):
        """네트워크가 막혀 있어도 예외 없이 끝나고 경고만 남아야 한다."""
        from keyword_maker.sources.live import LiveSources
        cfg = Config(sleep=0, timeout=2, use_trends=False, use_youtube=False)
        src = LiveSources(cfg)
        r = run(src, cfg, today="2026-01-01")
        self.assertFalse(r.demo)
        self.assertIsInstance(r.stock_ideas, list)


if __name__ == "__main__":
    unittest.main()
