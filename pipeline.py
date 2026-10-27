"""Pure DataFrame logic. No I/O."""

import re

import numpy as np
import pandas as pd

import config as cfg

DISBURSED_EVENTS = {"loan_disbursal_successful", "loans_taken_successfully", "loans_user_rate",
                    "transfer_transfer_status_check_started", "transfer_transfer_status_check_successful",
                    "transfer_save_receipt"}
REJECT_EVENTS = {"loan_approval_failed", "loans_ineligible"}

STAGE1_RETRY_EVENTS = {
    "onboarding_otp_verified_started", "onboarding_otp_verified_successful", "onboarding_otp_verified_failed",
    "login_start", "login_failed", "login_successful",
    "get_user_details_start", "get_user_details_successful", "get_user_details_failed",
    "get_kyc_start", "get_kyc_successful", "get_kyc_failed",
    "faq_get_faqs_list_started", "faq_get_faqs_list_successful",
}

OUT_COLS = ["base_date", "phone_number", "display_name", "channel", "drop_off_stage",
            "drop_off_time", "status", "priority_level", "total_session", "knock_off_reason"]


def norm_phone(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.0+)?", s):
        s = s.split(".")[0]
    elif re.fullmatch(r"[\d.]+[eE]\+?\d+", s):
        s = f"{float(s):.0f}"
    d = re.sub(r"\D", "", s)
    if not d:
        return None
    if d.startswith("234"):
        return d[:13]
    if d.startswith("0"):
        return "234" + d[1:11]
    if len(d) == 10:
        return "234" + d
    return d


def build_features(events: pd.DataFrame) -> pd.DataFrame:
    ev = events[events["stage_number"] > 0].copy()
    g  = ev.groupby("phone_number", sort=False)

    ev["prev_stage"]  = g["stage_number"].shift()
    ev["max_so_far"]  = g["stage_number"].cummax()
    ev["is_first"]    = g.cumcount() == 0
    ev["new_session"] = ev["is_first"] | (
        (ev["stage_number"] == 1) & (ev["max_so_far"] > 1) & (ev["prev_stage"] > 1)
    )
    ev["session_id"] = ev.groupby("phone_number")["new_session"].cumsum()

    sess = (ev.groupby(["phone_number", "session_id"])["event_timestamp"]
              .agg(lambda s: (s.max() - s.min()).total_seconds() / 60).rename("mins").reset_index())
    session_minutes = sess.groupby("phone_number")["mins"].sum()

    furthest = ev.groupby("phone_number")["stage_number"].max()
    at_top   = ev[ev["stage_number"] == ev["phone_number"].map(furthest)]
    stage_minutes = at_top.groupby("phone_number")["event_timestamp"].agg(
        lambda s: (s.max() - s.min()).total_seconds() / 60)

    gc = ev.groupby("phone_number")
    cust = pd.DataFrame({
        "display_name":         gc["display_name"].max(),
        "furthest_stage":       furthest,
        "total_sessions":       gc["session_id"].max(),
        "journey_start":        gc["event_timestamp"].min(),
        "drop_off_time":        gc["event_timestamp"].max(),
        "session_duration_min": session_minutes,
        "stage_duration_min":   stage_minutes,
        "rejected_in_journey":  gc["event"].agg(lambda s: int(s.isin(REJECT_EVENTS).any())),
        "is_disbursed":         gc["event"].agg(lambda s: int(s.isin(DISBURSED_EVENTS).any())),
        "approval_succeeded":   gc["event"].agg(lambda s: int((s == "loan_approval_successful").any())),
    }).fillna({"session_duration_min": 0, "stage_duration_min": 0}).reset_index()

    ev_sorted = ev.sort_values(["phone_number", "event_timestamp"])
    retry_counts = ev_sorted.groupby("phone_number", sort=False).apply(
        lambda g: _stage1_retries(g) + _fallback_retries(g)
    ).rename("retry_count")
    cust = cust.merge(retry_counts, on="phone_number", how="left")
    cust["retry_count"] = cust["retry_count"].fillna(0).astype(int)

    cust["drop_off_stage"] = cust.apply(_drop_off_label, axis=1)

    ge = events.groupby("phone_number")
    inv_only = (ge["is_investment_event"].max() == 1) & \
               (ge["is_loan_event"].max() == 0) & (ge["stage_number"].max() < 9)
    cust["is_investment"] = cust["phone_number"].map(inv_only).fillna(False).astype(int)

    cust["phone_number_norm"] = cust["phone_number"].map(norm_phone)
    return cust


def _stage1_retries(g_ev):
    seen_listed, prev_was_listed, retries = False, False, 0
    for ev_name, stg in zip(g_ev["event"].values, g_ev["stage_number"].values):
        is_listed = (stg == 1) and (ev_name in STAGE1_RETRY_EVENTS)
        if is_listed:
            if seen_listed and not prev_was_listed:
                retries += 1
            seen_listed = True
        prev_was_listed = is_listed
    return retries


def _fallback_retries(g_ev):
    fallback, max_seen, prev_stage = 0, 0, None
    for stg in g_ev["stage_number"].values:
        if stg == 1:
            prev_stage = stg
            continue
        if max_seen and stg < max_seen and stg != prev_stage:
            fallback += 1
        if stg > max_seen:
            max_seen = stg
        prev_stage = stg
    return fallback


def _drop_off_label(r):
    if r.is_disbursed:                                  return "completed"
    if r.rejected_in_journey:                           return "rejected"
    if r.furthest_stage == 12:                          return "reached_max_stage"
    if r.approval_succeeded or r.furthest_stage == 11:  return "approved_not_disbursed"
    if r.furthest_stage == 10:                          return "dropped_at_post_app_verification"
    if r.furthest_stage == 9:                           return "dropped_at_loan_application"
    if r.furthest_stage >= 2:                           return "kyc_dropoff"
    return "early_dropout"


def apply_pre_join_rules(cust: pd.DataFrame, hist: pd.DataFrame):
    already_rej = set(hist.loc[hist["knock_off_reason"] == cfg.REASON_INELIGIBLE, "phone_number"].dropna())
    already_dis = set(hist.loc[hist["knock_off_reason"] == cfg.REASON_DISBURSED,  "phone_number"].dropna())
    called_alr  = set(hist.loc[hist["status"] == "call", "phone_number"].dropna())

    cust["already_rejected"]  = cust["phone_number_norm"].isin(already_rej).astype(int)
    cust["already_disbursed"] = cust["phone_number_norm"].isin(already_dis).astype(int)
    cust["called_already"]    = cust["phone_number_norm"].isin(called_alr).astype(int)

    rules = [
        (cfg.REASON_ALREADY_REJECTED,  cust["already_rejected"] == 1),
        (cfg.REASON_ALREADY_DISBURSED, cust["already_disbursed"] == 1),
        (cfg.REASON_CALLED_ALREADY,    cust["called_already"] == 1),
        (cfg.REASON_DISBURSED,         cust["is_disbursed"] == 1),
        (cfg.REASON_INELIGIBLE,        cust["rejected_in_journey"] == 1),
        (cfg.REASON_INVESTMENT,        cust["is_investment"] == 1),
        (cfg.REASON_NO_INTENT,         (cust["furthest_stage"] == 1) & (cust["total_sessions"] == 1) & (cust["retry_count"] == 0)),
    ]
    cust["knock_off_reason"] = np.select([c for _, c in rules], [n for n, _ in rules], default="")
    cust["status"] = np.where(cust["knock_off_reason"] == "", "call", "no_call")

    return cust[cust["status"] == "no_call"].copy(), cust[cust["status"] == "call"].copy()


def apply_post_join_rules(to_join: pd.DataFrame, cj: pd.DataFrame, no_call_df: pd.DataFrame):
    df = to_join.merge(cj.drop(columns=["rn"]), on="phone_number", how="left")
    df["display_name"] = df["full_name"]

    chan = df["channels"].astype("string").fillna("")
    bad_channel = pd.Series(False, index=df.index)
    for pat in cfg.NO_CALL_CHANNEL_PATTERNS:
        bad_channel |= chan.str.contains(pat, flags=re.I, regex=True)

    rules = [
        (cfg.REASON_ACTIVE_LOAN, df["current_loan_status"] == "ACTIVE"),
        (cfg.REASON_INELIGIBLE,  df["decision_state"] == "REJECTED"),
        (cfg.REASON_FSA_OR_ON,   bad_channel),
    ]
    any_match = pd.Series(False, index=df.index)
    for _, c in rules:
        any_match |= c
    df["knock_off_reason"] = np.select([c for _, c in rules], [n for n, _ in rules], default="")
    df["channel"] = df["channels"]

    new_no_call = df[any_match].copy()
    new_no_call["status"] = "no_call"
    no_call_df = pd.concat([no_call_df, new_no_call], ignore_index=True)
    no_call_df = no_call_df.drop_duplicates("phone_number", keep="last").reset_index(drop=True)

    survivors = df[~any_match].copy()
    survivors["knock_off_reason"] = ""
    survivors["status"] = "call"

    assert not set(survivors["phone_number"]) & set(no_call_df["phone_number"])
    return survivors, no_call_df


def score_and_band(survivors: pd.DataFrame) -> pd.DataFrame:
    call_df = survivors.copy()
    raw = _score_raw(call_df)
    lo, hi = float(raw.min()), float(raw.max())
    if hi > lo:
        call_df["_floor_score"] = cfg.MIN_CALL_SCORE + (raw - lo) * (1.0 - cfg.MIN_CALL_SCORE) / (hi - lo)
    else:
        call_df["_floor_score"] = cfg.MIN_CALL_SCORE
    call_df["_floor_score"] = call_df["_floor_score"].clip(cfg.MIN_CALL_SCORE, 1.0)

    call_df["priority_level"] = call_df["_floor_score"].map(_band_call)
    order = {"Very High": 3, "High": 2, "Moderate": 1, "Low": 0}
    call_df = call_df.sort_values("priority_level", key=lambda s: s.map(order), ascending=False).reset_index(drop=True)

    assert (call_df["priority_level"] != "Low").all()
    return call_df


def _curve(x, cap):
    x = pd.to_numeric(x, errors="coerce").fillna(0).clip(lower=0, upper=cap)
    return np.log1p(x) / np.log1p(cap)


def _score_raw(d):
    max_score = (cfg.W_STAGE + cfg.W_RETRY + cfg.W_SESSION_DURATION
                 + cfg.W_STAGE_DURATION + cfg.W_STAGE_REPEAT)
    stage = d["furthest_stage"].clip(0, cfg.MAX_STAGE)
    retries = (d["total_sessions"] - 1).clip(lower=0)
    pts = (cfg.W_STAGE * stage / cfg.MAX_STAGE
           + cfg.W_RETRY * _curve(retries, cfg.MAX_RETRIES)
           + cfg.W_SESSION_DURATION * _curve(d["session_duration_min"], cfg.CAP_SESSION_MIN)
           + cfg.W_STAGE_DURATION * _curve(d["stage_duration_min"], cfg.CAP_STAGE_MIN)
           + cfg.W_STAGE_REPEAT * _curve(d.get("retry_count", 0), cfg.MAX_STAGE_REPEATS))
    return (pts / max_score).clip(lower=0, upper=1)


def _band_call(p):
    for name, cut in cfg.BAND_CUTOFFS:
        if p >= cut:
            return name
    return "Moderate"


def build_output(call_df: pd.DataFrame, no_call_df: pd.DataFrame, base_ts):
    def _build(frame, status):
        out = frame.copy()
        out["base_date"]        = base_ts
        out["phone_number"]     = out["phone_number"].map(norm_phone)
        out["status"]           = status
        out["total_session"]    = out["total_sessions"].astype(int)
        out["priority_level"]   = out["priority_level"] if "priority_level" in out else cfg.NO_CALL_BAND
        out["channel"]          = out["channel"] if "channel" in out else np.nan
        out["knock_off_reason"] = out["knock_off_reason"].fillna("") if "knock_off_reason" in out else ""
        return out[out["phone_number"].notna()].drop_duplicates("phone_number")

    out_call = _build(call_df, "call")
    out_nc   = _build(no_call_df, "no_call")
    out_nc["priority_level"] = cfg.NO_CALL_BAND
    out_call["knock_off_reason"] = np.nan
    return out_call[OUT_COLS], out_nc[OUT_COLS]