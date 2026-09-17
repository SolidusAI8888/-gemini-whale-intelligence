from __future__ import annotations

"""Declared tracking universe for the website.

Membership in this list means "monitor this filer/role".  It never creates a
trade, holding, chart marker, or concentration score.  Those still require a
separate verified disclosure in the trades table.
"""

WHITE_HOUSE_CABINET_URL = "https://www.whitehouse.gov/administration/cabinet/"
SENATE_DISCLOSURE_URL = "https://efdsearch.senate.gov/search/home/"
SEC_13F_URL = "https://www.sec.gov/divisions/investment/13ffaq"


CURRENT_EXECUTIVE_BRANCH = (
    ("Donald J. Trump", "President of the United States"),
    ("Scott Bessent", "Secretary of the Treasury"),
    ("Todd Blanche", "Attorney General"),
    ("Doug Burgum", "Secretary of the Interior"),
    ("Jay Clayton", "Director of National Intelligence"),
    ("Doug Collins", "Secretary of Veterans Affairs"),
    ("Sean Duffy", "Secretary of Transportation"),
    ("Jamieson Greer", "United States Trade Representative"),
    ("Pete Hegseth", "Secretary of War"),
    ("Robert F. Kennedy, Jr.", "Secretary of Health and Human Services"),
    ("Kelly Loeffler", "Administrator of the Small Business Administration"),
    ("Howard Lutnick", "Secretary of Commerce"),
    ("Linda McMahon", "Secretary of Education"),
    ("Markwayne Mullin", "Secretary of Homeland Security"),
    ("John Ratcliffe", "Director of the Central Intelligence Agency"),
    ("Brooke Rollins", "Secretary of Agriculture"),
    ("Marco Rubio", "Secretary of State"),
    ("Keith E. Sonderling", "Acting Secretary of Labor"),
    ("Scott Turner", "Secretary of Housing and Urban Development"),
    ("Russ Vought", "Director of the Office of Management and Budget"),
    ("Chris Wright", "Secretary of Energy"),
    ("Lee Zeldin", "Administrator of the Environmental Protection Agency"),
)

# Every senator with a parsed STOCK Act PTR on record since 2023 in the current
# reference snapshot.  Actual chart events still come only from an ingested PTR.
ACTIVE_SENATE_PTR_FILERS = (
    "Alan Armstrong", "Richard Blumenthal", "John Boozman", "David H. McCormick",
    "Thomas H. Tuberville", "Markwayne Mullin", "Sheldon Whitehouse", "John Fetterman",
    "Shelley M. Capito", "John R. Curtis", "Katie Britt", "Rick Scott", "Angus S. King",
    "Gary C. Peters", "John W. Hickenlooper", "Tina Smith", "Cory A. Booker", "Jerry Moran",
    "Bernie Moreno", "Lindsey Graham", "Mark R. Warner", "Timothy P. Sheehy",
    "A. Mitchell McConnell", "Susan M. Collins", "James Banks", "William F. Hagerty",
    "Christopher A. Coons", "M. Michael Rounds", "Ron L. Wyden",
)

# A stable minimum institutional baseline.  It combines the largest diversified
# U.S.-equity managers and the most consequential 13F reporting complexes.
TOP20_INSTITUTIONS = (
    "Vanguard Group", "BlackRock", "State Street Corp", "FMR LLC",
    "Capital Research Global Investors", "JPMorgan Asset Management",
    "Morgan Stanley Investment Management", "Goldman Sachs Asset Management",
    "Geode Capital Management", "Wellington Management Group",
    "T. Rowe Price Associates", "Invesco", "Northern Trust",
    "UBS Asset Management", "Bank of America Corp",
    "Charles Schwab Investment Management", "Dimensional Fund Advisors",
    "Norges Bank Investment Management", "Legal & General Investment Management",
    "Franklin Resources",
)

# Current named role-holders for every corporate core asset. Combined Chair/CEO
# roles intentionally appear once. BTC and PURR are excluded because they do not
# have a public-company board/officer structure that can file Form 4.
CORE_COMPANY_LEADERS = (
    ("MSTR", "Michael J. Saylor", "Executive Chairman"), ("MSTR", "Phong Le", "President & CEO"), ("MSTR", "Andrew Kang", "CFO"),
    ("NVDA", "Stephen C. Neal", "Lead Independent Director"), ("NVDA", "Jensen Huang", "Founder, President & CEO"), ("NVDA", "Colette Kress", "CFO"),
    ("TSLA", "Robyn Denholm", "Board Chair"), ("TSLA", "Elon Musk", "CEO"), ("TSLA", "Vaibhav Taneja", "CFO"),
    ("SPCX", "Elon Musk", "Chairman & CEO"), ("SPCX", "Bret Johnsen", "CFO"),
    ("GOOG", "John L. Hennessy", "Board Chair"), ("GOOG", "Sundar Pichai", "CEO"), ("GOOG", "Anat Ashkenazi", "CFO"),
    ("PLTR", "Peter Thiel", "Chairman"), ("PLTR", "Alexander Karp", "CEO"), ("PLTR", "David Glazer", "CFO"),
    ("ORCL", "Lawrence J. Ellison", "Chairman & CTO"), ("ORCL", "Clay Magouyrk", "Co-CEO"), ("ORCL", "Mike Sicilia", "Co-CEO"), ("ORCL", "Hilary Maxson", "CFO"),
    ("HOOD", "Vlad Tenev", "Chairman & CEO"), ("HOOD", "Shiv Verma", "CFO"),
    ("INTC", "Frank D. Yeary", "Board Chair"), ("INTC", "Lip-Bu Tan", "CEO"), ("INTC", "David Zinsner", "CFO"),
    ("MU", "Sanjay Mehrotra", "Chairman & CEO"), ("MU", "Mark Murphy", "CFO"),
    ("AAPL", "Arthur D. Levinson", "Board Chair"), ("AAPL", "Tim Cook", "CEO"), ("AAPL", "Kevan Parekh", "CFO"),
    ("AMZN", "Jeffrey P. Bezos", "Executive Chair"), ("AMZN", "Andy Jassy", "President & CEO"), ("AMZN", "Brian Olsavsky", "CFO"),
    ("AMD", "Lisa Su", "Chair & CEO"), ("AMD", "Jean Hu", "CFO"),
    ("GLW", "Wendell P. Weeks", "Chairman & CEO"), ("GLW", "Edward A. Schlesinger", "CFO"),
    ("MRVL", "Matt Murphy", "Chairman & CEO"), ("MRVL", "Willem Meintjes", "CFO"),
    ("MSFT", "Satya Nadella", "Chairman & CEO"), ("MSFT", "Amy Hood", "CFO"),
    ("UBER", "Ronald D. Sugar", "Independent Chair"), ("UBER", "Dara Khosrowshahi", "CEO"), ("UBER", "Prashanth Mahendra-Rajah", "CFO"),
    ("AVGO", "Harry L. You", "Chairman"), ("AVGO", "Hock E. Tan", "President & CEO"), ("AVGO", "Amie Thuener", "CFO"),
    ("RKLB", "Peter Beck", "Chairman, President & CEO"), ("RKLB", "Adam Spice", "CFO"),
)


def declared_whale_universe() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    executive_names = {name for name, _ in CURRENT_EXECUTIVE_BRANCH}
    for name, role in CURRENT_EXECUTIVE_BRANCH:
        rows.append({"name": name, "category": "行政部门", "weight": 1.0, "source": "OGE", "role": role, "source_url": WHITE_HOUSE_CABINET_URL, "tracking_status": "scope_only"})
    for name in ACTIVE_SENATE_PTR_FILERS:
        if name in executive_names:
            continue
        rows.append({"name": name, "category": "政界巨鲸", "weight": 1.0, "source": "Congress PTR", "role": "U.S. Senate · active PTR filer", "source_url": SENATE_DISCLOSURE_URL, "tracking_status": "scope_only"})
    for ticker, name, role in CORE_COMPANY_LEADERS:
        rows.append({"name": name, "category": "公司关键人员", "weight": 1.0, "source": "SEC Form 4", "role": f"{ticker} · {role}", "ticker": ticker, "source_url": "https://www.sec.gov/edgar/search/", "tracking_status": "scope_only"})
    for name in TOP20_INSTITUTIONS:
        rows.append({"name": name, "category": "重点机构", "weight": 0.9, "source": "SEC 13F", "role": "TOP20 institution tracking baseline", "source_url": SEC_13F_URL, "tracking_status": "scope_only"})
    return rows
