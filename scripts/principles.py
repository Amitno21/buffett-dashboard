"""A rotating Buffett principle for the learning panel.

These are summaries written for this dashboard, each pointing at the letter or
meeting where Buffett made the argument, so the reader can go and read the
original rather than relying on a paraphrase.
"""
from __future__ import annotations

from datetime import date

PRINCIPLES: list[dict[str, str]] = [
    {
        "title": "Owner earnings, not reported earnings",
        "body": "Reported profit ignores the capital a business must keep spending simply to stand still. "
                "Buffett's alternative is net income plus depreciation and other non-cash charges, minus "
                "the capital expenditure the business genuinely needs. Two companies can report identical "
                "earnings while one of them quietly consumes all of it just to maintain its position.",
        "source": "1986 shareholder letter, appendix on owner earnings",
    },
    {
        "title": "The moat is the asset",
        "body": "What protects a business matters more than what it earns this year. High returns attract "
                "competition, so the question is what stops rivals from taking those returns away: a brand "
                "customers insist on, costs nobody can match, or switching costs that make leaving painful.",
        "source": "1993 and 2007 shareholder letters",
    },
    {
        "title": "Price is what you pay, value is what you get",
        "body": "A wonderful business bought at a foolish price is a poor investment. The quality of the "
                "company and the attractiveness of the stock are two separate questions, and only the second "
                "one depends on today's price.",
        "source": "2008 shareholder letter",
    },
    {
        "title": "Margin of safety",
        "body": "Inherited from Benjamin Graham: build a bridge rated for far more weight than you intend to "
                "drive across it. Because every intrinsic-value estimate is an estimate, buy far enough below "
                "it that being somewhat wrong still leaves you whole.",
        "source": "Graham, The Intelligent Investor, ch. 20; endorsed repeatedly by Buffett",
    },
    {
        "title": "The circle of competence",
        "body": "The size of your circle matters far less than knowing exactly where its edge is. Buffett has "
                "passed on entire industries for decades, not because they were bad businesses, but because "
                "he could not confidently predict what they would look like in ten years.",
        "source": "1996 shareholder letter",
    },
    {
        "title": "Interest rates are gravity",
        "body": "The risk-free rate is what every asset must beat. When long-term government bonds yield very "
                "little, every other asset can justify a higher price; when they yield a lot, that same asset "
                "must get cheaper to stay competitive. Always compare an earnings yield with the ten-year.",
        "source": "1999 Sun Valley talk; recurring in annual meetings",
    },
    {
        "title": "The one-dollar premise",
        "body": "For every dollar a company keeps rather than pays out, it should create at least a dollar of "
                "market value over time. Retained earnings that fail this test would have been worth more in "
                "the shareholders' hands.",
        "source": "1984 shareholder letter",
    },
    {
        "title": "Be fearful when others are greedy",
        "body": "The market's mood is the source of opportunity, not information. Falling prices make a "
                "genuinely good business cheaper to own, which is good news for a buyer and bad news only for "
                "someone who has to sell.",
        "source": "1986 shareholder letter; New York Times op-ed, October 2008",
    },
    {
        "title": "Inactivity is a strategy",
        "body": "Buffett has described his favourite holding period as forever, and has said most investors "
                "would do better with a card allowing only twenty lifetime decisions. Every trade carries "
                "costs, taxes and the chance of being wrong; not trading carries none of them.",
        "source": "1988 and 1993 shareholder letters",
    },
    {
        "title": "Beware the institutional imperative",
        "body": "Organisations imitate their peers, resist changing direction, and find justifications for "
                "whatever leadership already wants to do. Buffett names this tendency as a major destroyer of "
                "capital and looks for managers who visibly resist it.",
        "source": "1989 shareholder letter",
    },
    {
        "title": "Time is the friend of the wonderful business",
        "body": "A mediocre company bought cheaply must be sold to make money. A great company compounds while "
                "you own it, which means the passage of time works for you rather than against you.",
        "source": "1989 shareholder letter",
    },
    {
        "title": "Debt turns a setback into a catastrophe",
        "body": "Leverage magnifies both outcomes, but only one of them can end the story. Buffett's preference "
                "for businesses that can fund themselves is a preference for surviving the years nobody "
                "forecast.",
        "source": "2010 shareholder letter",
    },
    {
        "title": "Look through to the earnings you own",
        "body": "A share is a fractional claim on a business. The right question is what your share of the "
                "company's earnings amounts to and whether that stream is growing, not what the quoted price "
                "did this week.",
        "source": "1991 shareholder letter",
    },
    {
        "title": "Buybacks only work below intrinsic value",
        "body": "Repurchasing stock above what the business is worth destroys value for the shareholders who "
                "stay, and creates it when done below. The same action can be excellent or wasteful depending "
                "entirely on price.",
        "source": "2011 and 2016 shareholder letters",
    },
    {
        "title": "Accounting earnings can be managed; cash is harder",
        "body": "Depreciation schedules, restructuring charges and one-off items all bend reported profit. "
                "Cash from operations, set against the capital spending needed to sustain it, is far harder "
                "to dress up.",
        "source": "2000 shareholder letter, on accounting shenanigans",
    },
    {
        "title": "Forecasts tell you about the forecaster",
        "body": "Buffett has consistently refused to base decisions on macroeconomic or market predictions, "
                "arguing that the analysable question is what a specific business will earn, not what the "
                "economy will do next year.",
        "source": "1994 shareholder letter",
    },
    {
        "title": "Diversification is protection against ignorance",
        "body": "Spreading capital thinly makes sense when you cannot tell one business from another. Buffett's "
                "point is not that concentration is safe, but that wide diversification and deep conviction "
                "are answers to different problems.",
        "source": "1993 shareholder letter",
    },
    {
        "title": "The cost of a bad manager compounds too",
        "body": "Buffett weights integrity and rationality in capital allocation as heavily as the economics of "
                "the business, because a manager who reinvests badly can waste a good company's advantages "
                "over many years.",
        "source": "1987 shareholder letter, on capital allocation",
    },
    {
        "title": "Cash is an option with no expiry",
        "body": "Holding cash costs you a little return while you wait, and pays you enormously when prices "
                "fall and nobody else can act. Berkshire's willingness to sit on large balances is a "
                "deliberate choice, not an accident.",
        "source": "2014 shareholder letter",
    },
    {
        "title": "Volatility is not risk",
        "body": "Buffett defines risk as the chance of permanent loss of capital, not the degree to which a "
                "price fluctuates. A stable price on a deteriorating business is far more dangerous than a "
                "volatile price on a sound one.",
        "source": "1993 shareholder letter",
    },
]


def principle_of_the_day(today: date | None = None) -> dict:
    """Deterministic daily rotation, so a given date always shows the same one."""
    today = today or date.today()
    index = today.toordinal() % len(PRINCIPLES)
    return {**PRINCIPLES[index], "index": index, "total": len(PRINCIPLES)}
