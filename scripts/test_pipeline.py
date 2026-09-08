"""Tests for the scoring and parsing logic.

Run with: python scripts/test_pipeline.py

These use the standard library only, so they run anywhere the build runs. Every
test below corresponds to a real defect found while building this pipeline; the
comments say which, so nobody re-introduces one by "simplifying" the code.
"""
from __future__ import annotations

import re
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import edgar  # noqa: E402
import metrics  # noqa: E402
import glossary  # noqa: E402
import israel  # noqa: E402
import summary  # noqa: E402
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


class TestSummaries(unittest.TestCase):
    """The prose layer. Each test here is a sentence that read badly on live data."""

    def company(self, score, grade, components, band="Above estimated value",
                available=True, caveats=None):
        return {
            "ticker": "TEST", "name": "TEST CORP /DE/",
            "quality": {"score": score, "grade": grade, "components": components,
                        "caveats": caveats or []},
            "valuation": {"available": available, "band": band, "base_value": 50.0,
                          "discount_to_value_pct": -20.0, "buy_below": 35.0,
                          "reason": "owner earnings are negative"},
            "price": {"price": 60.0},
        }

    def comp(self, key, points, maximum, value, label=None):
        return {"key": key, "points": points, "max": maximum, "value": value,
                "label": label or metrics.LABELS[key], "note": "", "detail": ""}

    def test_registrant_names_are_tidied(self):
        self.assertEqual(summary.clean_name("BANK OF AMERICA CORP /DE/"), "Bank of America Corp")
        self.assertEqual(summary.clean_name("COSTCO WHOLESALE CORP /NEW"), "Costco Wholesale Corp")
        self.assertEqual(summary.clean_name("Chubb Ltd"), "Chubb Ltd")

    def test_consistency_reads_as_words_not_a_fraction(self):
        text = summary.describe(self.comp("roe_consistency", 10, 10, "11/11"), positive=True)
        self.assertIn("11 of the last 11 years", text)
        self.assertNotIn("11/11", text)

    def test_zero_hits_is_not_phrased_as_only_zero(self):
        text = summary.describe(self.comp("roe_consistency", 0, 10, "0/11"), positive=False)
        self.assertIn("not once", text)
        self.assertNotIn("only 0", text)

    def test_tiny_sample_is_not_called_a_track_record(self):
        # Liberty Live cleared the bar in 2 of 2 years, which proves nothing.
        self.assertIsNone(summary.describe(self.comp("roe_consistency", 10, 10, "2/2"), positive=True))

    def test_a_loss_is_never_described_as_a_strength(self):
        self.assertIsNone(summary.describe(self.comp("roe_level", 0, 20, -6.9), positive=True))

    def test_a_loss_reads_as_losing_money(self):
        text = summary.describe(self.comp("roe_level", 0, 20, -6.9), positive=False)
        self.assertIn("losing money", text)
        self.assertNotIn("-7%", text)

    def test_return_basis_follows_the_component_label(self):
        equity = summary.describe(self.comp("roe_level", 20, 20, 25.0), positive=True)
        capital = summary.describe(
            self.comp("roe_level", 20, 20, 25.0, label="Return on invested capital"), positive=True)
        self.assertIn("shareholders have left in it", equity)
        self.assertIn("all the capital invested in it", capital)

    def test_retained_earnings_is_formatted_as_money(self):
        text = summary.describe(self.comp("retained_earnings", 10, 10, 1.7), positive=True)
        self.assertIn("$1.70", text)

    def test_a_poor_company_leads_with_its_problems(self):
        poor = self.company(19, "Poor", [
            self.comp("roe_level", 1, 20, 1.2),
            self.comp("margin_stability", 15, 15, 0.02),
        ])
        text = summary.company_summary(poor)
        problem = text.index("earns only")
        redeeming = text.index("It does score well")
        self.assertLess(problem, redeeming, "the weakness must come before the bright spot")

    def test_a_strong_company_leads_with_its_strengths(self):
        strong = self.company(90, "Exceptional", [
            self.comp("roe_level", 20, 20, 30.0),
            self.comp("earnings_consistency", 3, 15, 4),
        ])
        text = summary.company_summary(strong)
        self.assertLess(text.index("earns about 30%"), text.index("main mark against it"))

    def test_summaries_never_recommend(self):
        banned = ("you should", "we recommend", "a good buy", "worth buying",
                  "should buy", "should sell", "must buy")
        for score, grade, band in [(90, "Exceptional", "Below margin of safety"),
                                   (19, "Poor", "Above estimated value"),
                                   (52, "Adequate", "Near fair value")]:
            text = summary.company_summary(self.company(score, grade, [
                self.comp("roe_level", 20, 20, 25.0),
                self.comp("debt_burden", 0, 15, 9.0)], band=band)).lower()
            for phrase in banned:
                self.assertNotIn(phrase, text)

    def test_missing_valuation_explains_itself(self):
        text = summary.company_summary(self.company(
            10, "Poor", [self.comp("roe_level", 0, 20, -5.0)], available=False))
        self.assertIn("no usable estimate", text)

    def test_headline_is_short_and_covers_both_questions(self):
        headline = summary.quality_headline(self.company(
            90, "Exceptional", [], band="Below margin of safety"))
        self.assertEqual(headline, "Exceptional business, trading below the estimate")

    def test_brief_mentions_cheap_names_when_there_are_any(self):
        payload = {
            "weather": {"buffett_indicator": {"value": 218.0}, "treasury_10y": {"value": 4.77}},
            "companies": [self.company(60, "Adequate", [], band="Below margin of safety")],
            "signals": [],
        }
        brief = summary.daily_brief(payload)
        self.assertIn("218%", brief)
        self.assertIn("4.77%", brief)
        self.assertIn("TEST", brief)
        self.assertIn("not a recommendation", brief.replace("rather than a recommendation",
                                                            "not a recommendation"))

    def test_brief_handles_a_quiet_day(self):
        payload = {"weather": {}, "companies": [], "signals": []}
        brief = summary.daily_brief(payload)
        self.assertIn("Nothing of note", brief)

    def test_brief_leads_with_a_high_severity_signal(self):
        payload = {
            "weather": {},
            "companies": [self.company(60, "Adequate", [])],
            "signals": [{"severity": "low", "headline": "minor thing"},
                        {"severity": "high", "headline": "AAPL filed a new 10-K"}],
        }
        brief = summary.daily_brief(payload)
        self.assertIn("AAPL filed a new 10-K", brief)
        self.assertIn("1 other item", brief)



class TestIsrael(unittest.TestCase):
    """funder.co.il embeds each table as JSON in the page rather than as markup."""

    PAGE = (
        'blah blah\n\tvar somethingElse = {"x":[{"a":1}]};\n'
        '\tvar kaspitData = {"x":['
        '{"fundNum":123,"fundName":"  \u05db\u05e1\u05e4\u05d9\u05ea  \u05d0","fundMng":"\u05de\u05d9\u05d8\u05d1",'
        '"1day":0.02,"monthBegin":0.08,"yearBegin":2.7,"1year":4.03,"nihol":0.25,'
        '"hosafa":0.0,"rSize":4720.6,"lastUpdate":"2026-09-07"},'
        '{"fundNum":124,"fundName":"B","fundMng":"X","1day":0.01,"monthBegin":0.06,'
        '"yearBegin":2.6,"1year":null,"nihol":0.1,"hosafa":0.0,"rSize":100.0,'
        '"lastUpdate":"2026-09-07"}]};\n'
        'var after = 1;'
    )

    def test_extracts_the_named_variable_only(self):
        rows = israel.embedded_rows(self.PAGE, "kaspitData")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["fundNum"], 123)

    def test_missing_variable_returns_empty(self):
        self.assertEqual(israel.embedded_rows(self.PAGE, "notThere"), [])

    def test_malformed_json_does_not_raise(self):
        self.assertEqual(israel.embedded_rows('var kaspitData = {"x":[{oops}]};', "kaspitData"), [])

    def test_braces_inside_strings_do_not_end_the_object(self):
        page = 'var kaspitData = {"x":[{"fundName":"a } b","rSize":1.0}]};'
        rows = israel.embedded_rows(page, "kaspitData")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fundName"], "a } b")

    def test_names_are_whitespace_normalised(self):
        self.assertEqual(israel._clean("  \u05db\u05e1\u05e4\u05d9\u05ea   \u05d0  "),
                         "\u05db\u05e1\u05e4\u05d9\u05ea \u05d0")

    def test_num_tolerates_blanks_and_nulls(self):
        self.assertIsNone(israel._num(None))
        self.assertIsNone(israel._num(""))
        self.assertIsNone(israel._num("abc"))
        self.assertEqual(israel._num("2.5"), 2.5)

    def test_brief_always_says_the_buffett_tests_do_not_apply(self):
        # These are funds, not operating businesses. Someone arriving on this tab
        # must not read the quality scores as applying to them.
        brief = israel.brief({
            "indices": [{"label": "TA-125", "price": 4230.0, "change_pct": 0.71,
                         "from_high_pct": -5.6}],
            "shekel": {"rate": 3.007},
            "money_market": {"available": True, "count": 44, "median_year_pct": 3.97,
                             "median_fee_pct": 0.169},
            "hedge": {"available": True, "count": 46, "median_year_pct": 14.6,
                      "worst_year_pct": -11.1, "best_year_pct": 55.6,
                      "negative_year_count": 5, "with_year_history": 46,
                      "typical_performance_fee_pct": 20.0},
        })
        self.assertIn("None of the Buffett tests", brief)
        self.assertIn("TA-125", brief)
        self.assertIn("performance fee", brief)
        self.assertIn("3.97", brief)   # the money-market median reaches the text
        self.assertIn("14.6", brief)   # and the hedge-fund median

    def test_brief_survives_every_source_being_down(self):
        brief = israel.brief({"indices": [], "shekel": {},
                              "money_market": {"available": False},
                              "hedge": {"available": False}})
        self.assertTrue(brief.strip())


class TestGlossary(unittest.TestCase):
    def test_every_term_has_a_real_definition(self):
        for section in glossary.GLOSSARY:
            self.assertTrue(section["group"].strip())
            self.assertTrue(section["blurb"].strip())
            for term, definition in section["terms"]:
                self.assertTrue(term.strip(), section["group"])
                self.assertGreater(len(definition), 40, f"{term} is too thin to help")

    def test_no_duplicate_terms(self):
        seen = [t for s in glossary.GLOSSARY for t, _ in s["terms"]]
        self.assertEqual(len(seen), len(set(seen)), "a term is defined twice")

    def test_payload_shape_matches_the_renderer(self):
        payload = glossary.as_payload()
        self.assertEqual(len(payload), len(glossary.GLOSSARY))
        first = payload[0]
        self.assertEqual(set(first), {"group", "blurb", "terms"})
        self.assertEqual(set(first["terms"][0]), {"term", "definition"})
        self.assertEqual(sum(len(g["terms"]) for g in payload), glossary.term_count())

    # Terms that mean nothing to a newcomer. If the interface uses one, the
    # glossary has to explain it.
    JARGON = [
        "GDP", "survivorship", "Form 4", "Bank of Israel", "owner earnings",
        "margin of safety", "moat", "intrinsic value", "circle of competence",
        "return on equity", "return on invested capital", "ROE", "ROIC",
        "gross margin", "capex", "capital expenditure", "depreciation",
        "impairment", "buyback", "retained earnings", "free cash flow",
        "book equity", "diluted", "shares outstanding", "discounted cash flow",
        "discount rate", "terminal value", "terminal growth", "earnings yield",
        "P/E", "bear", "bull", "Buffett Indicator", "VIX", "Treasury",
        "market cap", "index", "moving average", "RSI", "ATR", "52-week",
        "SEC", "EDGAR", "XBRL", "10-K", "10-Q", "8-K", "13F", "Berkshire",
        "money-market", "hedge fund", "management fee", "performance fee",
        "exposure profile", "long/short", "TA-125", "TA-35", "Tel Bond", "shekel",
    ]

    @staticmethod
    def _whole_word(term: str):
        return re.compile(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])")

    def test_no_jargon_reaches_the_reader_undefined(self):
        """Scan what the interface actually says, not a list written from memory.

        The earlier version of this test checked a handful of terms chosen by
        hand, so it passed while the page displayed "218% of GDP" with GDP
        defined nowhere. This reads the real interface sources instead.
        """
        root = Path(__file__).resolve().parent.parent
        sources = [
            root / "docs" / "index.html",   # the page shell
            root / "docs" / "app.js",       # every literal string the renderer writes
            root / "scripts" / "summary.py",  # generated company and daily prose
            root / "scripts" / "israel.py",   # generated Israeli prose
        ]
        ui_text = "\n".join(p.read_text(encoding="utf-8") for p in sources if p.exists()).lower()
        # Match against the glossary *headings* only. Checking the whole
        # glossary text is too lax: "GDP" appeared inside the Buffett Indicator
        # definition, which let an earlier version of this test pass while GDP
        # itself had no entry. A word mentioned in passing is not defined.
        headings = " | ".join(
            term for section in glossary.GLOSSARY for term, _ in section["terms"]
        ).lower()

        undefined = [
            term for term in self.JARGON
            if self._whole_word(term).search(ui_text)
            and not self._whole_word(term).search(headings)
        ]
        self.assertEqual(undefined, [],
                         f"used in the interface but has no glossary entry: {undefined}")



if __name__ == "__main__":
    unittest.main(verbosity=2)
