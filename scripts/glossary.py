"""Every concept the dashboard uses, explained for someone new to investing.

Written to be read start to finish, not just looked up: the groups go in the
order the dashboard actually reasons in. Plain words, concrete numbers, and no
term used inside a definition before it has been defined.
"""
from __future__ import annotations

GLOSSARY: list[dict] = [
    {
        "group": "The idea behind the whole dashboard",
        "blurb": "Warren Buffett buys pieces of businesses, not tickets on share prices. "
                 "Everything here follows from that.",
        "terms": [
            ("A share", "A slice of ownership in a real company. Owning one share of a company "
                        "with a million shares means you own a millionth of its profits, its "
                        "buildings and its debts. The price on the screen is just what somebody "
                        "will pay you for that slice today."),
            ("Value investing", "Working out what a business is genuinely worth, then buying only "
                                "if the market is asking less than that. The opposite is guessing "
                                "which way the price will move next."),
            ("Intrinsic value", "What the business is actually worth, based on the cash it will "
                                "produce for its owners over its life. Nobody can know it exactly; "
                                "every figure on this dashboard is an estimate with its "
                                "assumptions shown."),
            ("Margin of safety", "Only buying at a decent discount to your estimate, because your "
                                 "estimate might be wrong. If you think a business is worth $100 a "
                                 "share and you insist on paying under $70, you can be 30% too "
                                 "optimistic and still not lose money."),
            ("Moat", "Whatever stops competitors from stealing a company's profits: a brand people "
                     "insist on, costs nobody can match, or the sheer hassle of switching away. "
                     "Without one, high profits attract rivals until the profits are gone."),
            ("Circle of competence", "The set of businesses you actually understand well enough to "
                                     "judge. Buffett treats staying inside it as non-negotiable, "
                                     "and it is the one test no dashboard can run for you."),
        ],
    },
    {
        "group": "Reading a company's accounts",
        "blurb": "Companies must publish their finances. These are the numbers the dashboard "
                 "pulls out of those filings.",
        "terms": [
            ("Revenue", "All the money that came in from selling things, before any costs. Also "
                        "called sales or the top line."),
            ("Net income", "What is left after every cost, including tax. Also called profit, "
                           "earnings, or the bottom line."),
            ("Book equity (book value)", "What the owners would in theory have left if the company sold "
                                    "everything and paid off all its debts. It comes from the "
                                    "accounts, not the stock market."),
            ("Return on equity (ROE)", "Profit divided by that owners' stake: how much the company "
                                       "earns on the money shareholders have left in it. Buffett "
                                       "looks for 15% or more, held for years. A company earning "
                                       "$15 on every $100 of owners' money is a far better machine "
                                       "than one earning $3."),
            ("Return on invested capital (ROIC)", "The same idea, but counting borrowed money too. "
                                                  "The dashboard switches to this when a company "
                                                  "has bought back so much of its own stock that "
                                                  "its book equity is near zero and ROE stops "
                                                  "meaning anything."),
            ("Gross margin", "Of every $100 of sales, how much survives after the direct cost of "
                             "making the product. A steady gross margin over ten years is the best "
                             "outside evidence that a moat is real."),
            ("Capital expenditure (capex)", "Money spent on physical things the business needs: "
                                            "factories, machines, shops, servers. It is real cash "
                                            "leaving the company even though it is not counted as "
                                            "a cost in the profit line straight away."),
            ("Depreciation", "The accountant's way of spreading the cost of equipment over the "
                             "years it is used, rather than all at once. It is a bookkeeping "
                             "entry, not cash going out of the door this year."),
            ("Owner earnings", "Buffett's own measure, and the one this dashboard values companies "
                               "on: profit, plus bookkeeping charges like depreciation that did "
                               "not really cost cash, minus the capital spending genuinely needed "
                               "to keep the business where it is. It answers what an owner could "
                               "actually take out each year without the business shrinking."),
            ("Free cash flow", "A close cousin: the cash generated by operations minus all capital "
                               "spending, including spending on growth."),
            ("Impairment / write-down", "An admission that something the company owns is worth less "
                                        "than the books said, often a business it overpaid for. It "
                                        "hits reported profit hard but no cash moves, which is why "
                                        "the dashboard adds it back."),
            ("Shares outstanding", "How many slices the company is divided into. It matters "
                                   "enormously: the same business split into twice as many shares "
                                   "means each share is worth half as much."),
            ("Buyback", "A company using its cash to purchase its own shares and cancel them, so "
                        "each remaining share owns a bigger slice. Good value when the shares are "
                        "cheap, wasteful when they are expensive."),
            ("Retained earnings", "Profits the company kept and reinvested instead of paying out. "
                                  "Buffett's test is that every $1 kept should eventually create at "
                                  "least $1 of market value, or shareholders would have been "
                                  "better off with the cash."),
        ],
    },
    {
        "group": "Working out what a business is worth",
        "blurb": "How the dashboard turns those numbers into a price per share.",
        "terms": [
            ("Discounted cash flow (DCF)", "The method behind the estimate. Add up the cash the "
                                           "business should produce over the next ten years plus a "
                                           "value for everything after that, then shrink those "
                                           "future amounts to reflect that money later is worth "
                                           "less than money now."),
            ("Discount rate", "The annual return you insist on for taking the risk, used to shrink "
                              "those future amounts. Higher discount rate, lower value today. The "
                              "dashboard defaults to 10% and lets you change it with a slider."),
            ("Terminal value", "The lump that stands for everything the business earns beyond year "
                               "ten. It is usually half or more of any DCF result, which is worth "
                               "knowing: most of the 'value' rests on a guess about the distant "
                               "future. Each company page shows what share it makes up."),
            ("Terminal growth", "How fast you assume the business grows forever after year ten. It "
                                "has to be modest, because nothing grows faster than the whole "
                                "economy indefinitely. The default here is 2.5%."),
            ("Earnings yield", "Profit divided by the price you pay, expressed as a percentage. It "
                               "lets you compare a share directly with a savings account or a "
                               "government bond."),
            ("P/E ratio", "Price divided by annual profit per share. A P/E of 25 means you are "
                          "paying 25 years of current profit for the stake. Lower is cheaper, all "
                          "else being equal, but all else rarely is."),
            ("Bear, base and bull case", "The same calculation run on pessimistic, middling and "
                                         "optimistic growth assumptions, so you see a range rather "
                                         "than one falsely precise number."),
        ],
    },
    {
        "group": "The wider market",
        "blurb": "Context for whether shares in general are cheap or dear right now.",
        "terms": [
            ("Index (S&P 500, TA-125)", "A basket tracking many companies at once, used as "
                                        "shorthand for how a whole market is doing. The S&P 500 "
                                        "holds 500 large American firms; TA-125 holds the 125 "
                                        "largest in Tel Aviv."),
            ("GDP", "Gross domestic product: the total value of everything a country produces in a "
                    "year. It is the standard measure of how big an economy is, and it is the "
                    "figure the stock market gets compared against just below."),
            ("Buffett Indicator", "The value of every listed company added together, divided by "
                                  "GDP. So a reading of 200% means the stock market is worth twice "
                                  "everything the country produces in a year. Buffett called it "
                                  "the best single measure of whether shares are expensive. Around "
                                  "100% is historically normal; today's reading is far above that."),
            ("US Treasury (government bond yield)", "A Treasury is a loan to the American "
                                                    "government, and its yield is what that loan "
                                                    "pays you. It counts as the safest return "
                                                    "available, so Buffett calls it gravity: every "
                                                    "share has to beat it, or you should simply buy "
                                                    "the bond instead. The 10-year Treasury is the "
                                                    "one quoted on this page."),
            ("VIX", "A gauge of how much turbulence traders expect in the next month. High means "
                    "fear, low means calm — and calm markets are usually expensive ones."),
            ("Market capitalisation", "The price of one share multiplied by the number of shares: "
                                      "what the market says the whole company is worth."),
            ("Survivorship bias", "The trap of judging by the winners because the losers have "
                                  "quietly disappeared from the list. A table of the best-performing "
                                  "funds looks wonderful precisely because the failures are not in "
                                  "it. Any ranked list on this page, including the fund tables, has "
                                  "to be read with that in mind."),
        ],
    },
    {
        "group": "Short-term measures",
        "blurb": "A different discipline entirely. These say nothing about what a business is "
                 "worth, and are on the dashboard only for timing a purchase you have already "
                 "decided on.",
        "terms": [
            ("Moving average", "The average closing price over the last 50 or 200 days, which "
                               "smooths out the daily noise. Price above the long average is "
                               "conventionally read as an uptrend."),
            ("RSI", "A 0-100 score of how hard a share has been bought or sold lately. Above 70 is "
                    "called overbought, below 30 oversold. It is a crowd-mood reading, not a "
                    "statement about the business."),
            ("ATR / volatility", "How much the price typically moves in a day. Useful for deciding "
                                 "how large a position you can hold without a normal wobble forcing "
                                 "you to sell."),
            ("52-week high and low", "The highest and lowest the price has been in the past year. "
                                     "A share near its low is not automatically cheap, but it is a "
                                     "reasonable place to start looking."),
        ],
    },
    {
        "group": "Where the numbers come from",
        "blurb": "American companies must file their accounts publicly. This dashboard reads those "
                 "filings directly rather than trusting a summary.",
        "terms": [
            ("SEC", "The US Securities and Exchange Commission, the regulator that requires listed "
                    "companies to publish their finances honestly and on time."),
            ("EDGAR", "The SEC's free public archive where all those filings live."),
            ("10-K", "The annual report: a company's full audited accounts for the year, plus a "
                     "discussion of its risks and business."),
            ("10-Q", "The lighter quarterly version, filed three times a year."),
            ("8-K", "A one-off announcement of something significant between reports, such as an "
                    "acquisition or a chief executive leaving."),
            ("13F", "A quarterly list every large investment manager must file showing what US "
                    "shares they own. This is how the dashboard knows what Berkshire Hathaway "
                    "holds — though it arrives up to 45 days late."),
            ("Berkshire Hathaway", "The company Buffett has run since 1965, and the vehicle through "
                                   "which he invests."),
            ("XBRL", "The machine-readable tagging inside modern filings that lets software read a "
                     "balance sheet without a human retyping it."),
        ],
    },
    {
        "group": "The Israeli page",
        "blurb": "Israeli terms used on the Israel tab. These are funds rather than operating "
                 "companies, so none of the Buffett tests above apply to them.",
        "terms": [
            ("Money-market fund (קרן כספית)", "A fund holding very short-term, very safe debt. The "
                                              "closest thing to cash that still pays interest: no "
                                              "lock-up, minimal risk, and a yield that follows the "
                                              "Bank of Israel's rate. Useful as the benchmark "
                                              "anything riskier has to beat."),
            ("Hedge fund in trust (קרן גידור בנאמנות)", "An Israeli fund allowed to use strategies "
                                                        "ordinary funds cannot, such as betting "
                                                        "that a share will fall. Sold to the public "
                                                        "in a regulated wrapper, but with higher "
                                                        "fees and much wider outcomes."),
            ("Management fee (דמי ניהול)", "The percentage the manager charges every year, whether "
                                           "or not they make you money. On a money-market fund it "
                                           "matters enormously, because it comes straight out of a "
                                           "small return."),
            ("Performance fee (דמי הצלחה)", "An extra cut of the profits, typically 20% among the "
                                            "Israeli hedge funds listed here. It means the return "
                                            "you read in the table is not the return that reaches "
                                            "your pocket."),
            ("Exposure profile (e.g. 5E)", "An Israeli labelling rule. The digit is how much can be "
                                           "in shares (0 = none, 6 = up to 200%), and the letter is "
                                           "foreign-currency exposure (A = none, F = up to 200%). "
                                           "So 5E means a lot of both."),
            ("Long/short", "A fund that both owns shares it expects to rise and bets against shares "
                           "it expects to fall. It can profit in a falling market, and can also "
                           "lose in a rising one."),
            ("TA-125 / TA-35", "The main Tel Aviv indices: the 125 largest listed Israeli "
                               "companies, and the 35 largest within them."),
            ("Tel Bond (תל בונד)", "The family of Tel Aviv indices tracking corporate bonds rather "
                                   "than shares."),
            ("Bank of Israel rate", "The interest rate Israel's central bank sets, which is the "
                                    "anchor for what every safe shekel investment pays. When it "
                                    "rises, money-market funds pay more within weeks; when it "
                                    "falls, they pay less. It is the Israeli equivalent of the "
                                    "Treasury yield as a hurdle."),
            ("Shekel rate (USD/ILS)", "How many shekels one US dollar buys. It matters because the "
                                      "American companies on the other tabs are priced in dollars, "
                                      "so a stronger shekel quietly reduces their value to you."),
        ],
    },
]


def term_count() -> int:
    return sum(len(section["terms"]) for section in GLOSSARY)


def as_payload() -> list[dict]:
    """Shape for the dashboard payload."""
    return [
        {
            "group": section["group"],
            "blurb": section["blurb"],
            "terms": [{"term": term, "definition": definition}
                      for term, definition in section["terms"]],
        }
        for section in GLOSSARY
    ]
