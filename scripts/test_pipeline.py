"""Tests for the scoring and parsing logic.

Run with: python scripts/test_pipeline.py

These use the standard library only, so they run anywhere the build runs. Every
test below corresponds to a real defect found while building this pipeline; the
comments say which, so nobody re-introduces one by "simplifying" the code.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import edgar  # noqa: E402
import metrics  # noqa: E402
from common import cagr, safe_div  # noqa: E402
from principles import PRINCIPLES, principle_of_the_day  # noqa: E402


def facts_from(**series) -> dict:
    """Build a financials dict in the shape extract_financials returns."""
    return {name: dict(values) for name, values in series.items()}


class TestHelpers(unittest.TestCase):
    def test_safe_div_handles_zero_and_none(self):
        self.assertIsNone(safe_div(1, 0))
        self.assertIsNone(safe_div(None, 5))
        self.assertIsNone(safe_div(5, None))
        self.assertAlmostEqual(safe_div(10, 4), 2.5)

    def test_cagr_rejects_non_positive_start(self):
        self.assertIsNone(cagr(0, 100, 5))
        self.assertIsNone(cagr(-10, 100, 5))
        self.assertIsNone(cagr(100, 200, 0))
        self.assertAlmostEqual(cagr(100, 200, 10), 0.0717735, places=6)

    def test_ramp_clamps_at_both_ends(self):
        self.assertEqual(metrics.ramp(0.30, 0.08, 0.18, 20), 20)   # above target
        self.assertEqual(metrics.ramp(0.02, 0.08, 0.18, 20), 0)    # below floor
        self.assertEqual(metrics.ramp(0.13, 0.08, 0.18, 20), 10)   # midpoint
        self.assertEqual(metrics.ramp(None, 0.08, 0.18, 20), 0)

    def test_ramp_runs_backwards_for_lower_is_better(self):
        # Leverage: 1x should score full, 8x zero.
        self.assertEqual(metrics.ramp(1.0, 8.0, 1.0, 15), 15)
        self.assertEqual(metrics.ramp(8.0, 8.0, 1.0, 15), 0)


class TestOwnerEarnings(unittest.TestCase):
    def test_maintenance_capex_is_capped_at_depreciation(self):
        # Growth capex above depreciation must not be charged against owner
        # earnings: 100 + 20 - min(50, 20) = 100.
        fin = facts_from(net_income={2024: 100}, depreciation={2024: 20}, capex={2024: 50})
        self.assertEqual(metrics.owner_earnings(fin, 2024), 100)

    def test_capex_below_depreciation_is_charged_in_full(self):
        # 100 + 20 - min(5, 20) = 115.
        fin = facts_from(net_income={2024: 100}, depreciation={2024: 20}, capex={2024: 5})
        self.assertEqual(metrics.owner_earnings(fin, 2024), 115)

    def test_impairment_is_added_back(self):
        # Regression: Kraft Heinz's 2025 goodwill write-down drove owner
        # earnings negative until non-cash impairments were added back.
        fin = facts_from(net_income={2024: -500}, depreciation={2024: 100},
                         capex={2024: 100}, impairment={2024: 900})
        self.assertEqual(metrics.owner_earnings(fin, 2024), 400)

    def test_missing_net_income_yields_none(self):
        self.assertIsNone(metrics.owner_earnings(facts_from(depreciation={2024: 5}), 2024))

    def test_string_and_int_years_are_interchangeable(self):
        # Years become strings after a JSON round trip through the cache.
        fin = {"net_income": {"2024": 100}, "depreciation": {"2024": 20}, "capex": {"2024": 50}}
        self.assertEqual(metrics.owner_earnings(fin, 2024), 100)


class TestShareCount(unittest.TestCase):
    def test_prefers_diluted_over_issued(self):
        # Regression: Coca-Cola's CommonStockSharesIssued is 7.04bn including
        # treasury stock, against 4.31bn genuinely outstanding.
        fin = facts_from(diluted_shares={2025: 4.31e9}, shares_out={2025: 7.04e9},
                         net_income={2025: 1e9})
        shares, source = metrics.share_count(fin)
        self.assertEqual(shares, 4.31e9)
        self.assertIn("diluted", source)

    def test_derives_from_eps_when_diluted_missing(self):
        fin = facts_from(net_income={2025: 1000}, eps_diluted={2025: 2.0})
        shares, source = metrics.share_count(fin)
        self.assertEqual(shares, 500)
        self.assertIn("EPS", source)

    def test_rejects_stale_counts(self):
        # Regression: Visa's only undimensioned cover-page figure is from 2009.
        # Using it valued the company off a sixth of its real share count.
        fin = facts_from(cover_shares={2009: 470e6}, net_income={2025: 1e9})
        shares, source = metrics.share_count(fin)
        self.assertIsNone(shares)
        self.assertIn("no share count", source)

    def test_accepts_recent_cover_page_count(self):
        fin = facts_from(cover_shares={2024: 1.9e9}, net_income={2025: 1e9})
        shares, source = metrics.share_count(fin)
        self.assertEqual(shares, 1.9e9)
        self.assertIn("cover page", source)


class TestQualityScore(unittest.TestCase):
    def steady_business(self) -> tuple[dict, dict]:
        fin = facts_from(
            net_income={y: 100 * 1.10 ** (y - 2015) for y in range(2015, 2026)},
            equity={y: 500 for y in range(2015, 2026)},
            revenue={y: 1000 for y in range(2015, 2026)},
            gross_profit={y: 600 for y in range(2015, 2026)},
            depreciation={y: 50 for y in range(2015, 2026)},
            capex={y: 50 for y in range(2015, 2026)},
            long_term_debt={y: 100 for y in range(2015, 2026)},
            operating_income={y: 200 for y in range(2015, 2026)},
            cash={y: 50 for y in range(2015, 2026)},
        )
        return fin, metrics.build_series(fin)

    def test_a_steady_compounder_scores_well(self):
        fin, derived = self.steady_business()
        result = metrics.quality_score(fin, derived)
        self.assertGreater(result["score"], 70)
        self.assertIn(result["grade"], {"Strong", "Exceptional"})

    def test_components_sum_to_the_total(self):
        fin, derived = self.steady_business()
        result = metrics.quality_score(fin, derived)
        self.assertAlmostEqual(sum(c["points"] for c in result["components"]),
                               result["score"], places=1)

    def test_weights_sum_to_one_hundred(self):
        self.assertEqual(sum(metrics.WEIGHTS.values()), 100)

    def test_every_component_is_reported_even_without_data(self):
        result = metrics.quality_score({}, {})
        self.assertEqual(len(result["components"]), len(metrics.WEIGHTS))
        self.assertEqual(result["score"], 0)

    def test_mild_earnings_dip_is_not_penalised_like_a_collapse(self):
        # Regression: counting every down year equally scored Coca-Cola 0/15.
        mild = facts_from(net_income={2020: 100, 2021: 98, 2022: 105, 2023: 103, 2024: 110})
        severe = facts_from(net_income={2020: 100, 2021: 40, 2022: 105, 2023: 30, 2024: 110})
        mild_pts = next(c for c in metrics.quality_score(mild, metrics.build_series(mild))["components"]
                        if c["key"] == "earnings_consistency")["points"]
        severe_pts = next(c for c in metrics.quality_score(severe, metrics.build_series(severe))["components"]
                          if c["key"] == "earnings_consistency")["points"]
        self.assertEqual(mild_pts, metrics.WEIGHTS["earnings_consistency"])
        self.assertLess(severe_pts, mild_pts)

    def test_negative_equity_falls_back_to_return_on_capital(self):
        # Regression: Mastercard printed 193% ROE and DaVita -166% purely
        # because buybacks had driven book equity near zero.
        fin = facts_from(
            net_income={y: 100 for y in range(2020, 2026)},
            equity={y: -50 for y in range(2020, 2026)},
            assets={y: 1000 for y in range(2020, 2026)},
            revenue={y: 500 for y in range(2020, 2026)},
            operating_income={y: 150 for y in range(2020, 2026)},
            long_term_debt={y: 400 for y in range(2020, 2026)},
            cash={y: 20 for y in range(2020, 2026)},
        )
        result = metrics.quality_score(fin, metrics.build_series(fin))
        component = next(c for c in result["components"] if c["key"] == "roe_level")
        self.assertIn("invested capital", component["note"] + component["detail"])
        self.assertTrue(any("buyback" in c for c in result["caveats"]))

    def test_financial_companies_are_flagged(self):
        fin = facts_from(net_income={y: 100 for y in range(2020, 2026)},
                         equity={y: 800 for y in range(2020, 2026)},
                         revenue={y: 500 for y in range(2020, 2026)})
        result = metrics.quality_score(fin, metrics.build_series(fin))
        self.assertTrue(any("financial company" in c for c in result["caveats"]))


class TestValuation(unittest.TestCase):
    settings = {"margin_of_safety_pct": 30, "discount_rate_pct": 10.0, "terminal_growth_pct": 2.5}

    def test_dcf_is_higher_when_growth_is_higher(self):
        low = metrics.discounted_owner_earnings(100, 10, growth_1_5=0.02, growth_6_10=0.02,
                                                discount=0.10, terminal_growth=0.025)
        high = metrics.discounted_owner_earnings(100, 10, growth_1_5=0.10, growth_6_10=0.08,
                                                 discount=0.10, terminal_growth=0.025)
        self.assertGreater(high["per_share"], low["per_share"])

    def test_dcf_is_lower_when_discount_rate_is_higher(self):
        cheap = metrics.discounted_owner_earnings(100, 10, growth_1_5=0.05, growth_6_10=0.05,
                                                  discount=0.08, terminal_growth=0.025)
        dear = metrics.discounted_owner_earnings(100, 10, growth_1_5=0.05, growth_6_10=0.05,
                                                 discount=0.14, terminal_growth=0.025)
        self.assertGreater(cheap["per_share"], dear["per_share"])

    def test_dcf_refuses_when_terminal_growth_exceeds_discount(self):
        # Otherwise the Gordon formula divides by a negative and returns nonsense.
        self.assertIsNone(metrics.discounted_owner_earnings(
            100, 10, growth_1_5=0.05, growth_6_10=0.05, discount=0.03, terminal_growth=0.05))

    def test_dcf_rejects_zero_shares(self):
        self.assertIsNone(metrics.discounted_owner_earnings(
            100, 0, growth_1_5=0.05, growth_6_10=0.05, discount=0.10, terminal_growth=0.025))

    def test_median_base_survives_one_write_down_year(self):
        # Regression: a mean over three years let a single impairment year make
        # a sound business look unvaluable.
        fin = facts_from(
            net_income={2021: 300, 2022: 310, 2023: 320, 2024: 330, 2025: -900},
            equity={y: 2000 for y in range(2021, 2026)},
            revenue={y: 3000 for y in range(2021, 2026)},
            cash={2025: 100}, long_term_debt={2025: 50},
        )
        derived = metrics.build_series(fin)
        result = metrics.valuation(derived, fin, price=50, shares=100, settings=self.settings)
        self.assertTrue(result["available"])
        self.assertGreater(result["base_owner_earnings"], 0)

    def test_missing_share_count_explains_the_override(self):
        fin = facts_from(net_income={2024: 100}, equity={2024: 500}, revenue={2024: 900})
        result = metrics.valuation(metrics.build_series(fin), fin, price=50, shares=None,
                                   settings=self.settings)
        self.assertFalse(result["available"])
        self.assertIn("shares_override", result["reason"])

    def test_bands_follow_the_margin_of_safety(self):
        fin = facts_from(
            net_income={y: 100 for y in range(2016, 2026)},
            equity={y: 500 for y in range(2016, 2026)},
            revenue={y: 1000 for y in range(2016, 2026)},
        )
        derived = metrics.build_series(fin)
        expensive = metrics.valuation(derived, fin, price=1e6, shares=100, settings=self.settings)
        cheap = metrics.valuation(derived, fin, price=0.01, shares=100, settings=self.settings)
        self.assertEqual(expensive["band"], "Above estimated value")
        self.assertEqual(cheap["band"], "Below margin of safety")


class TestEdgarParsing(unittest.TestCase):
    INFO_TABLE = b"""<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable>
        <nameOfIssuer>COCA COLA CO</nameOfIssuer><titleOfClass>COM</titleOfClass>
        <cusip>191216100</cusip><value>32500000000</value>
        <shrsOrPrnAmt><sshPrnamt>400000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      </infoTable>
      <infoTable>
        <nameOfIssuer>COCA COLA CO</nameOfIssuer><titleOfClass>COM</titleOfClass>
        <cusip>191216100</cusip><value>500000000</value>
        <shrsOrPrnAmt><sshPrnamt>6000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      </infoTable>
      <infoTable>
        <nameOfIssuer>SOME PUT</nameOfIssuer><titleOfClass>COM</titleOfClass>
        <cusip>999999999</cusip><value>1000</value>
        <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt></shrsOrPrnAmt><putCall>Put</putCall>
      </infoTable>
    </informationTable>"""

    def test_share_count_field_casing(self):
        # Regression: the schema element is sshPrnamt, with a lower-case 'a'.
        # Matching sshPrnAmt exactly returned zero shares for every holding.
        rows = edgar.parse_information_table(self.INFO_TABLE)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["shares"], 400000000)

    def test_holdings_are_consolidated_per_issuer(self):
        merged = edgar.consolidate_holdings(edgar.parse_information_table(self.INFO_TABLE))
        coke = next(h for h in merged if h["cusip"] == "191216100")
        self.assertEqual(coke["shares"], 406000000)
        self.assertEqual(coke["value"], 33000000000)

    def test_options_are_excluded(self):
        merged = edgar.consolidate_holdings(edgar.parse_information_table(self.INFO_TABLE))
        self.assertNotIn("999999999", {h["cusip"] for h in merged})

    def test_name_normalisation_strips_corporate_suffixes(self):
        self.assertEqual(edgar.normalise_name("Apple Inc."), "APPLE")
        self.assertEqual(edgar.normalise_name("COCA COLA CO"), "COCA COLA")
        self.assertEqual(edgar.normalise_name("BANK OF AMER CORP /DE/"), "BANK OF AMER DE")

    def test_annual_series_merges_across_tag_changes(self):
        # Regression: ASC 606 renamed the revenue tag in 2018, so first-match
        # wins truncated a decade of history to nine years.
        facts = {"facts": {"us-gaap": {
            "SalesRevenueNet": {"units": {"USD": [
                {"frame": "CY2015", "val": 100}, {"frame": "CY2016", "val": 110}]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                {"frame": "CY2017", "val": 120}, {"frame": "CY2018", "val": 130}]}},
        }}}
        series = edgar.annual_series(facts, "revenue")
        self.assertEqual(sorted(series), [2015, 2016, 2017, 2018])

    def test_preferred_tag_wins_on_overlapping_years(self):
        facts = {"facts": {"us-gaap": {
            "SalesRevenueNet": {"units": {"USD": [{"frame": "CY2017", "val": 999}]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [{"frame": "CY2017", "val": 120}]}},
        }}}
        self.assertEqual(edgar.annual_series(facts, "revenue")[2017], 120)

    def test_instant_concepts_use_year_end_frames(self):
        facts = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [
            {"frame": "CY2023Q2I", "val": 1},     # mid-year, ignored
            {"frame": "CY2023Q4I", "val": 500},
        ]}}}}}
        self.assertEqual(edgar.annual_series(facts, "assets"), {2023: 500})

    def test_filing_url_strips_accession_dashes(self):
        url = edgar.filing_url(320193, "0000320193-25-000073", "aapl-20250927.htm")
        self.assertIn("/320193/000032019325000073/aapl-20250927.htm", url)


class TestPrinciples(unittest.TestCase):
    def test_rotation_is_deterministic_and_in_range(self):
        first = principle_of_the_day(date(2026, 1, 1))
        again = principle_of_the_day(date(2026, 1, 1))
        self.assertEqual(first["title"], again["title"])
        self.assertEqual(first["total"], len(PRINCIPLES))

    def test_consecutive_days_differ(self):
        a = principle_of_the_day(date(2026, 1, 1))["title"]
        b = principle_of_the_day(date(2026, 1, 2))["title"]
        self.assertNotEqual(a, b)

    def test_every_principle_cites_a_source(self):
        for p in PRINCIPLES:
            self.assertTrue(p["source"].strip(), f"{p['title']} has no source")
            self.assertTrue(p["body"].strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
