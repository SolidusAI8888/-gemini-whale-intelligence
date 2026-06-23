CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    company_name TEXT,
    cik TEXT,
    accession_number TEXT,
    filing_url TEXT,
    whale_name TEXT NOT NULL,
    whale_category TEXT NOT NULL,
    insider_role TEXT,
    action TEXT NOT NULL,
    transaction_code TEXT,
    amount_usd REAL,
    shares REAL,
    price REAL,
    trade_date TEXT,
    filing_date TEXT,
    source TEXT NOT NULL,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_dates ON trades(filing_date, trade_date);
CREATE INDEX IF NOT EXISTS idx_trades_action ON trades(action);
CREATE INDEX IF NOT EXISTS idx_trades_whale ON trades(whale_name, whale_category);

CREATE TABLE IF NOT EXISTS scores (
    ticker TEXT PRIMARY KEY,
    buy_score REAL DEFAULT 0,
    sell_score REAL DEFAULT 0,
    whale_score REAL DEFAULT 0,
    consensus_score REAL DEFAULT 0,
    opportunity_score REAL DEFAULT 0,
    risk_score REAL DEFAULT 0,
    signal_label TEXT,
    explanation TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT,
    new_trade_count INTEGER DEFAULT 0,
    report_path TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    ticker TEXT PRIMARY KEY,
    price REAL,
    change_pct REAL,
    volume REAL,
    ret_20d REAL,
    ret_60d REAL,
    sma20 REAL,
    sma50 REAL,
    week_52_high REAL,
    week_52_low REAL,
    pe_ratio REAL,
    ps_ratio REAL,
    peg_ratio REAL,
    revenue_growth_yoy REAL,
    profit_margin REAL,
    gross_margin REAL,
    net_margin REAL,
    market_cap REAL,
    beta REAL,
    news_buzz REAL,
    news_sentiment_score REAL,
    news_bearish_percent REAL,
    finnhub_insider_buy_count INTEGER,
    finnhub_insider_sell_count INTEGER,
    finnhub_insider_buy_amount REAL,
    finnhub_insider_sell_amount REAL,
    trend_score REAL,
    valuation_score REAL,
    sentiment_score REAL,
    data_sources TEXT,
    summary_note TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_updated ON market_snapshots(updated_at);
