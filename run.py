"""Orchestration: pull → features → rules → journey → score → write → download."""

import os
from pathlib import Path

import pandas as pd
import redshift_connector
from dotenv import load_dotenv

load_dotenv()               # ← load .env FIRST

import config as cfg        # ← now REDSHIFT_PASSWORD is in os.environ
import pipeline
import queries


def run_sql(sql: str) -> pd.DataFrame:
    with redshift_connector.connect(**cfg.REDSHIFT) as conn, conn.cursor() as cur:
        cur.execute(sql)
        df = cur.fetch_dataframe()
    return df if df is not None else pd.DataFrame()


def main():
    print(f"window: [{cfg.LOOKBACK_HOURS_MAX}h ago, {cfg.LOOKBACK_HOURS_MIN}h ago)")

    # 1. Pull Mixpanel events
    events = run_sql(queries.events_sql(cfg.LOOKBACK_HOURS_MIN, cfg.LOOKBACK_HOURS_MAX))
    events = events[events["phone_number"].notna()].copy()
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"])
    events = events.sort_values(["phone_number", "event_timestamp", "event"]).reset_index(drop=True)
    print(f"{len(events):,} events | {events.phone_number.nunique():,} phones")

    # 2. Features + retry_count
    cust = pipeline.build_features(events)

    # 3. Historical lookback (today excluded)
    hist = run_sql(queries.lookback_sql(cfg.TELESALES_TABLE, cfg.LOOKBACK_DAYS))
    hist["phone_number"] = hist["phone_number"].map(pipeline.norm_phone)
    print(f"lookback rows (last {cfg.LOOKBACK_DAYS} days): {len(hist):,}")

    # 4. Pre-join knock-offs
    no_call_df, to_join = pipeline.apply_pre_join_rules(cust, hist)
    print(f"call: {len(to_join):,} | no_call: {len(no_call_df):,}")

    # 5. Journey lookup
    phones = to_join["phone_number"].dropna().drop_duplicates().tolist()
    phone_list_sql = ",".join(f"'{p}'" for p in phones)
    cj = run_sql(queries.journey_sql(phone_list_sql, cfg.USE_JOURNEY_WINDOW, cfg.JOURNEY_LOOKBACK_HOURS))
    cj["created_at"] = pd.to_datetime(cj["created_at"])
    print(f"journey rows: {len(cj):,}")

    # 6. Post-join knock-offs
    survivors, no_call_df = pipeline.apply_post_join_rules(to_join, cj, no_call_df)
    print(f"survivors: {len(survivors):,} | no_call: {len(no_call_df):,}")

    # 7. Score
    call_df = pipeline.score_and_band(survivors)
    print(call_df["priority_level"].value_counts().to_string())

    # 8. Build output frames
    base_ts = pd.Timestamp.now().floor("s")
    out_call, out_nc = pipeline.build_output(call_df, no_call_df, base_ts)
    print(f"call: {len(out_call):,} | no_call: {len(out_nc):,}")

    # 9. Insert into Redshift
    _insert(cfg.TELESALES_TABLE, out_call, out_nc, base_ts)

    # 10. Download today's call list
    _download_call_list(out_call, base_ts)


def _insert(table, out_call, out_nc, base_ts):
    all_rows = pd.concat([out_call, out_nc], ignore_index=True)
    today_date = base_ts.strftime("%Y-%m-%d")

    def esc(v):
        if pd.isna(v):
            return "NULL"
        return "'" + str(v).replace("'", "''") + "'"

    def row_value(r):
        dot = pd.to_datetime(r["drop_off_time"])
        return (
            f"(DATE '{today_date}', {esc(r['phone_number'])}, {esc(r['display_name'])}, "
            f"{esc(r['channel'])}, {esc(r['drop_off_stage'])}, "
            f"TIMESTAMP '{dot:%Y-%m-%d %H:%M:%S}', "
            f"{esc(r['status'])}, {esc(r['priority_level'])}, "
            f"{int(r['total_session'])}, {esc(r['knock_off_reason'])})"
        )

    values = [row_value(r) for _, r in all_rows.iterrows()]
    insert_cols = ("(base_date, phone_number, display_name, channel, drop_off_stage, drop_off_time, "
                   "status, priority_level, total_session, knock_off_reason)")

    batch = 500
    inserted = 0
    with redshift_connector.connect(**cfg.REDSHIFT) as conn, conn.cursor() as cur:
        for i in range(0, len(values), batch):
            chunk = values[i:i+batch]
            cur.execute(f"INSERT INTO {table} {insert_cols} VALUES\n" + ",\n".join(chunk))
            inserted += len(chunk)
        conn.commit()
    print(f"inserted {inserted:,} rows")


def _download_call_list(out_call, base_ts):
    leads_dir = Path(cfg.LEADS_DIR)
    leads_dir.mkdir(parents=True, exist_ok=True)
    today = base_ts.strftime("%Y-%m-%d")
    out_path = leads_dir / f"call_list_{today}.csv"
    if out_path.exists():
        out_path = leads_dir / f"call_list_{today}_{base_ts:%H%M%S}.csv"

    order = {"Very High": 3, "High": 2, "Moderate": 1}
    dl = out_call.sort_values("priority_level", key=lambda s: s.map(order), ascending=False).reset_index(drop=True)
    dl.to_csv(out_path, index=False)
    print(f"downloaded {len(dl):,} call rows -> {out_path}")


if __name__ == "__main__":
    main()