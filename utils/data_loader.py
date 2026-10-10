import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TENDERS_PATH = BASE_DIR / "data" / "gem_tenders.csv"
BIDS_PATH = BASE_DIR / "data" / "demo_bids.csv"

TENDER_SCHEMA = [
    "tender_id", "item_name", "department", "start_date", "end_date",
    "status", "quantity", "official_url", "source_type", "source_document",
]

BID_SCHEMA = [
    "tender_id", "bidder_id", "bid_amount", "bid_timestamp",
    "outcome", "product_category", "source_type",
]


def load_tenders() -> pd.DataFrame:
    try:
        df = pd.read_csv(TENDERS_PATH)
        # Ensure all expected columns exist
        for col in TENDER_SCHEMA:
            if col not in df.columns:
                df[col] = pd.NA
        return df[TENDER_SCHEMA].dropna(how="all")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=TENDER_SCHEMA)


def load_bids() -> pd.DataFrame:
    try:
        df = pd.read_csv(BIDS_PATH)
        for col in BID_SCHEMA:
            if col not in df.columns:
                df[col] = pd.NA
        return df[BID_SCHEMA].dropna(how="all")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=BID_SCHEMA)
