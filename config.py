"""Runtime config. Committed to git. Only the password comes from .env."""

import os

# --- Redshift ---------------------------------------------------------------
REDSHIFT = {
    "host":     "ox-datawarehouse-cls.chkhpbcphj8j.eu-west-1.redshift.amazonaws.com",
    "port":     5439,
    "database": "ox_datawarehouse",
    "user":     "oxygen_qa",
    "password": os.environ["REDSHIFT_PASSWORD"],  # from .env
}

TELESALES_TABLE = '"ox_datawarehouse"."oxygenx"."telesales_dropoff"'

# --- Mixpanel analysis window (production: last 24 hours) -------------------
LOOKBACK_HOURS_MIN = 0
LOOKBACK_HOURS_MAX = 92

# --- telesales_dropoff historical lookback (today always excluded) ----------
LOOKBACK_DAYS = 14

# --- Journey window (parked until refresh fix; ignored while USE_JOURNEY_WINDOW=False) ---
JOURNEY_LOOKBACK_HOURS = 48
USE_JOURNEY_WINDOW     = False

# --- Output CSV -------------------------------------------------------------
LEADS_DIR = "output"

# --- Scoring weights --------------------------------------------------------
W_STAGE            = 75.0
MAX_STAGE          = 12
W_RETRY            = 35.0
MAX_RETRIES        = 6
W_SESSION_DURATION = 5.0
CAP_SESSION_MIN    = 60
W_STAGE_DURATION   = 4.0
CAP_STAGE_MIN      = 30
W_STAGE_REPEAT     = 3.0
MAX_STAGE_REPEATS  = 3

# --- Bands (fractions of MAX_SCORE) -----------------------------------------
BAND_CUTOFFS   = [("Very High", 0.70), ("High", 0.50), ("Moderate", 0.20)]
MIN_CALL_SCORE = 0.2001
NO_CALL_BAND   = "Low"

# --- Knock-off reason labels ------------------------------------------------
REASON_NO_INTENT          = "No_intent"
REASON_INELIGIBLE         = "ineligible"
REASON_DISBURSED          = "disbursed"
REASON_ACTIVE_LOAN        = "active_loan"
REASON_INVESTMENT         = "investment"
REASON_FSA_OR_ON          = "FSA/ON"
REASON_ALREADY_REJECTED   = "already_rejected"
REASON_ALREADY_DISBURSED  = "already_disbursed"
REASON_CALLED_ALREADY     = "called_already"

# --- No-call channel patterns ----------------------------------------------
NO_CALL_CHANNEL_PATTERNS = [r"(?i)\bfsa\b", r"(?i)oxygen[\s_-]*now"]
