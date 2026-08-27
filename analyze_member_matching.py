"""
analyze_member_matching.py — Standalone diagnostic script.

Analyzes whether MEMBER_ID improves cross-source matching quality
between Registro (registro_rcv.csv) and Talleres (talleres.csv).

Does NOT modify any pipeline code or production data.
Reads from data/raw/ using the existing extractors.

Run from the project root:
    python analyze_member_matching.py

Output: console report + optional CSV exports to data/analysis/
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))


# ── Constants ─────────────────────────────────────────────────────────────────

ANALYSIS_DIR = Path("data/analysis")
SEPARATOR = "-" * 52


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_email(series: pd.Series) -> pd.Series:
    """Lowercase + strip — same normalization used in transform.py."""
    return series.astype(str).str.strip().str.lower().replace("nan", pd.NA)


def _normalize_member_id(series: pd.Series) -> pd.Series:
    """
    Normalize MEMBER_ID to string for safe comparison across sources.
    Registro may store it as int64, Talleres as object.
    Coerces both to stripped string, treating 0 and NaN as NA.
    """
    normalized = (
        pd.to_numeric(series, errors="coerce")
        .where(lambda x: x > 0)
        .astype("Int64")
        .astype(str)
        .replace("<NA>", pd.NA)
        .replace("nan", pd.NA)
    )
    return normalized


def _load_source(source_name: str) -> pd.DataFrame:
    """
    Load a source using the existing extractor (includes CSV repair,
    encoding detection and column mapping — identical to what the
    pipeline uses). Falls back to empty DataFrame on failure.
    """
    try:
        if source_name == "registro":
            from scripts.extractors.registro_extractor import RegistroExtractor
            df = RegistroExtractor().extract()
        elif source_name == "talleres":
            from scripts.extractors.talleres_extractor import TalleresExtractor
            df = TalleresExtractor().extract()
        else:
            raise ValueError(f"Unknown source: {source_name}")
        print(f"  Loaded {source_name}: {len(df):,} rows, {len(df.columns)} columns")
        return df
    except Exception as exc:
        print(f"  ERROR loading {source_name}: {exc}")
        return pd.DataFrame()


def _export_csv(df: pd.DataFrame, filename: str) -> None:
    """Save a DataFrame to data/analysis/ for manual inspection."""
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    path = ANALYSIS_DIR / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  Exported: {path} ({len(df):,} rows)")


# ── Analysis functions ────────────────────────────────────────────────────────

def q1_q2_unique_member_ids(
    reg: pd.DataFrame,
    tal: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """
    Q1: Unique MEMBER_ID in Registro.
    Q2: Unique MEMBER_ID in Talleres.

    Returns normalized ID series for reuse in subsequent questions.
    """
    reg_ids = _normalize_member_id(reg.get("member_id", pd.Series(dtype=str)))
    tal_ids = _normalize_member_id(tal.get("member_id", pd.Series(dtype=str)))
    return reg_ids, tal_ids


def q3_member_id_overlap(
    reg_ids: pd.Series,
    tal_ids: pd.Series,
) -> set:
    """
    Q3: MEMBER_ID values present in BOTH sources.
    These are the candidates that MEMBER_ID matching could recover.
    """
    reg_set = set(reg_ids.dropna().unique())
    tal_set = set(tal_ids.dropna().unique())
    return reg_set & tal_set


def q4_email_matches(
    reg: pd.DataFrame,
    tal: pd.DataFrame,
) -> pd.DataFrame:
    """
    Q4: Users already matched by email (current algorithm, pass 1).
    Returns the joined DataFrame for reuse.
    """
    reg_email = _normalize_email(reg.get("email", pd.Series(dtype=str)))
    tal_email = _normalize_email(tal.get("email", pd.Series(dtype=str)))

    reg_work = reg.copy()
    tal_work = tal.copy()
    reg_work["email_norm"] = reg_email
    tal_work["email_norm"] = tal_email

    matched = pd.merge(
        reg_work[["email_norm", "member_id"]].rename(
            columns={"member_id": "reg_member_id"}
        ).dropna(subset=["email_norm"]),
        tal_work[["email_norm", "member_id", "formulario_entry_id"]].rename(
            columns={"member_id": "tal_member_id"}
        ).dropna(subset=["email_norm"]),
        on="email_norm",
        how="inner",
    )
    return matched


def q5_email_and_member_id_agree(matched: pd.DataFrame) -> pd.DataFrame:
    """
    Q5: Of email-matched records, how many also share the same MEMBER_ID?
    High agreement = MEMBER_ID is a reliable secondary key.
    Low agreement = IDs diverged (data entry issue or source inconsistency).
    """
    reg_ids = _normalize_member_id(matched["reg_member_id"])
    tal_ids = _normalize_member_id(matched["tal_member_id"])

    both_present = reg_ids.notna() & tal_ids.notna()
    agree = both_present & (reg_ids == tal_ids)
    return matched[agree]


def q6_same_member_id_different_email(
    reg: pd.DataFrame,
    tal: pd.DataFrame,
) -> pd.DataFrame:
    """
    Q6: Records with matching MEMBER_ID but different (or missing) email.
    These are the users that MEMBER_ID matching could ADDITIONALLY recover
    beyond what email already captures — the core metric for this analysis.
    """
    reg_work = reg.copy()
    tal_work = tal.copy()

    reg_work["email_norm"]     = _normalize_email(reg.get("email", pd.Series(dtype=str)))
    reg_work["member_id_norm"] = _normalize_member_id(reg.get("member_id", pd.Series(dtype=str)))
    tal_work["email_norm"]     = _normalize_email(tal.get("email", pd.Series(dtype=str)))
    tal_work["member_id_norm"] = _normalize_member_id(tal.get("member_id", pd.Series(dtype=str)))

    # Join on MEMBER_ID
    id_matched = pd.merge(
        reg_work[["email_norm", "member_id_norm"]].rename(
            columns={"email_norm": "reg_email", "member_id_norm": "member_id_norm"}
        ).dropna(subset=["member_id_norm"]),
        tal_work[["email_norm", "member_id_norm", "formulario_entry_id"]].rename(
            columns={"email_norm": "tal_email"}
        ).dropna(subset=["member_id_norm"]),
        on="member_id_norm",
        how="inner",
    )

    # Keep only those where emails differ or at least one is missing
    email_differs = (
        id_matched["reg_email"].isna()
        | id_matched["tal_email"].isna()
        | (id_matched["reg_email"] != id_matched["tal_email"])
    )
    return id_matched[email_differs].copy()


def q7_q8_duplicate_member_ids(
    reg: pd.DataFrame,
    tal: pd.DataFrame,
    reg_ids: pd.Series,
    tal_ids: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Q7: Duplicated MEMBER_ID in Registro (same ID, different rows).
    Q8: Duplicated MEMBER_ID in Talleres (expected — same user, multiple workshops).

    Duplicates in Registro are a data quality concern: if one MEMBER_ID maps
    to multiple emails, using it as a join key could produce incorrect matches.
    """
    reg_dup_ids  = reg_ids[reg_ids.notna() & reg_ids.duplicated(keep=False)]
    reg_dups     = reg.loc[reg_dup_ids.index].copy()
    reg_dups["member_id_norm"] = reg_ids[reg_dup_ids.index]

    tal_dup_ids  = tal_ids[tal_ids.notna() & tal_ids.duplicated(keep=False)]
    tal_dups     = tal.loc[tal_dup_ids.index].copy()
    tal_dups["member_id_norm"] = tal_ids[tal_dup_ids.index]

    return reg_dups, tal_dups


def q9_email_matches_member_id_differs(matched: pd.DataFrame) -> pd.DataFrame:
    """
    Q9: Records where email matches but MEMBER_ID differs.
    These are conflicting signals — suggests a user changed their MEMBER_ID
    or that IDs were assigned differently across sources.
    High conflict rate = MEMBER_ID is unreliable as a secondary key.
    """
    reg_ids = _normalize_member_id(matched["reg_member_id"])
    tal_ids = _normalize_member_id(matched["tal_member_id"])

    both_present = reg_ids.notna() & tal_ids.notna()
    conflict     = both_present & (reg_ids != tal_ids)
    return matched[conflict]


def q10_potential_additional_matches(
    additional: pd.DataFrame,
    reg_dups: pd.DataFrame,
) -> dict:
    """
    Q10: Estimate additional recoverable users if MEMBER_ID were used.

    Adjusts for Registro duplicates: a MEMBER_ID that maps to multiple
    emails in Registro cannot be used safely as a join key without
    additional disambiguation logic.
    """
    unsafe_ids = set(
        _normalize_member_id(reg_dups.get("member_id", pd.Series(dtype=str)))
        .dropna()
        .unique()
    )

    additional_norm = additional.copy()
    additional_norm["member_id_norm_check"] = _normalize_member_id(
        additional.get("member_id_norm", pd.Series(dtype=str))
    )

    safe_additional = additional_norm[
        ~additional_norm["member_id_norm_check"].isin(unsafe_ids)
    ]
    unsafe_additional = additional_norm[
        additional_norm["member_id_norm_check"].isin(unsafe_ids)
    ]

    return {
        "total_additional":  len(additional),
        "safe_additional":   len(safe_additional),
        "unsafe_additional": len(unsafe_additional),
        "unsafe_ids":        len(unsafe_ids),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print(SEPARATOR)
    print("  MEMBER_ID Matching Analysis")
    print("  Unified Data Insights Platform — diagnostic only")
    print(SEPARATOR)
    print()

    # ── Load sources ──────────────────────────────────────────────────────────
    print("Loading sources via existing extractors...")
    reg = _load_source("registro")
    tal = _load_source("talleres")
    print()

    if reg.empty or tal.empty:
        print("ERROR: One or both sources failed to load. Cannot continue.")
        sys.exit(1)

    # ── Run questions ─────────────────────────────────────────────────────────
    reg_ids, tal_ids = q1_q2_unique_member_ids(reg, tal)

    n_reg_users          = len(reg)
    n_reg_unique_ids     = reg_ids.dropna().nunique()
    n_tal_users          = len(tal)
    n_tal_unique_ids     = tal_ids.dropna().nunique()

    id_overlap           = q3_member_id_overlap(reg_ids, tal_ids)
    n_id_overlap         = len(id_overlap)

    email_matched        = q4_email_matches(reg, tal)
    n_email_matches      = email_matched["email_norm"].nunique()

    email_and_id_agree   = q5_email_and_member_id_agree(email_matched)
    n_agree              = len(email_and_id_agree)

    additional           = q6_same_member_id_different_email(reg, tal)
    n_additional_raw     = len(additional)

    reg_dups, tal_dups   = q7_q8_duplicate_member_ids(reg, tal, reg_ids, tal_ids)
    n_reg_dups           = reg_ids.dropna()[reg_ids.dropna().duplicated(keep=False)].nunique()
    n_tal_dups           = tal_ids.dropna()[tal_ids.dropna().duplicated(keep=False)].nunique()

    conflicts            = q9_email_matches_member_id_differs(email_matched)
    n_conflicts          = len(conflicts)

    potential            = q10_potential_additional_matches(additional, reg_dups)

    # ── Agreement rate (trust signal for MEMBER_ID) ───────────────────────────
    email_matched_with_both_ids = email_matched[
        _normalize_member_id(email_matched["reg_member_id"]).notna()
        & _normalize_member_id(email_matched["tal_member_id"]).notna()
    ]
    n_with_both = len(email_matched_with_both_ids)
    agreement_rate = (
        (n_agree / n_with_both * 100) if n_with_both > 0 else 0.0
    )
    conflict_rate = (
        (n_conflicts / n_with_both * 100) if n_with_both > 0 else 0.0
    )

    # ── Optional CSV exports ──────────────────────────────────────────────────
    print("Exporting detail CSVs to data/analysis/ ...")
    if not additional.empty:
        _export_csv(
            additional,
            "potential_member_id_matches.csv",
        )
    if not conflicts.empty:
        _export_csv(
            conflicts[["email_norm", "reg_member_id", "tal_member_id"]],
            "conflicting_member_ids.csv",
        )
    if not reg_dups.empty:
        _export_csv(
            reg_dups[["member_id_norm", "email"]].drop_duplicates(),
            "registro_duplicate_member_ids.csv",
        )
    print()

    # ── Report ────────────────────────────────────────────────────────────────
    print(SEPARATOR)
    print("  Matching Analysis Report")
    print(SEPARATOR)
    print(f"  Registro users:                    {n_reg_users:>8,}")
    print(f"  Registro unique MEMBER_ID:         {n_reg_unique_ids:>8,}")
    print(f"  Talleres inscriptions:             {n_tal_users:>8,}")
    print(f"  Talleres unique MEMBER_ID:         {n_tal_unique_ids:>8,}")
    print()
    print(f"  MEMBER_ID overlap (both sources):  {n_id_overlap:>8,}")
    print()
    print(f"  Email matches (current algo):      {n_email_matches:>8,}")
    print(f"  Of those — MEMBER_ID also agrees:  {n_agree:>8,}  ({agreement_rate:.1f}% of records with both IDs)")
    print(f"  Of those — MEMBER_ID conflicts:    {n_conflicts:>8,}  ({conflict_rate:.1f}% of records with both IDs)")
    print()
    print(f"  Same MEMBER_ID, different email:   {n_additional_raw:>8,}  (raw potential additional matches)")
    print(f"    Safe to use (no dup risk):        {potential['safe_additional']:>7,}")
    print(f"    Unsafe (ambiguous dup in Reg):    {potential['unsafe_additional']:>7,}")
    print()
    print(f"  Duplicate MEMBER_ID in Registro:   {n_reg_dups:>8,}  unique IDs with 2+ rows")
    print(f"  Duplicate MEMBER_ID in Talleres:   {n_tal_dups:>8,}  unique IDs with 2+ rows (expected)")
    print(SEPARATOR)

    # ── Recommendation ────────────────────────────────────────────────────────
    print()
    print("  Recommendation")
    print(SEPARATOR)

    # Decision logic based on evidence
    safe_gain_pct = (
        potential["safe_additional"] / n_reg_users * 100
        if n_reg_users > 0 else 0.0
    )
    is_reliable   = agreement_rate >= 95.0
    has_safe_gain = potential["safe_additional"] >= 50
    has_conflicts = conflict_rate > 2.0

    if is_reliable and has_safe_gain and not has_conflicts:
        recommendation = "Use MEMBER_ID as secondary fallback (after email)"
        rationale = (
            f"MEMBER_ID is highly reliable ({agreement_rate:.1f}% agreement on "
            f"email-matched records) and would recover {potential['safe_additional']:,} "
            f"additional users ({safe_gain_pct:.1f}% of Registro) with low conflict "
            f"risk ({conflict_rate:.1f}%). Implementing it as a secondary fallback "
            f"in consolidate.py after the email pass is the recommended next step."
        )
    elif is_reliable and not has_safe_gain:
        recommendation = "Keep email as primary key — MEMBER_ID gain is marginal"
        rationale = (
            f"MEMBER_ID is reliable ({agreement_rate:.1f}% agreement) but would only "
            f"recover {potential['safe_additional']:,} additional users ({safe_gain_pct:.1f}%). "
            f"The engineering cost of adding a secondary matching pass outweighs "
            f"the gain at this volume. Revisit when the dataset grows."
        )
    elif has_conflicts:
        recommendation = "Do not use MEMBER_ID — conflict rate too high"
        rationale = (
            f"MEMBER_ID conflicts on {conflict_rate:.1f}% of email-matched records "
            f"where both IDs are present. This suggests the ID is not stable across "
            f"sources (reassigned, re-entered, or inconsistently populated). "
            f"Using it as a join key would introduce incorrect matches."
        )
    else:
        recommendation = "Insufficient evidence — inspect exported CSVs manually"
        rationale = (
            f"The data does not produce a clear signal. Review "
            f"data/analysis/potential_member_id_matches.csv and "
            f"data/analysis/conflicting_member_ids.csv before deciding."
        )

    print(f"  {recommendation}")
    print()
    # Wrap rationale at 70 chars
    words  = rationale.split()
    line   = "  "
    for word in words:
        if len(line) + len(word) + 1 > 72:
            print(line)
            line = "  " + word + " "
        else:
            line += word + " "
    if line.strip():
        print(line)

    print()
    print(SEPARATOR)
    print()


if __name__ == "__main__":
    main()
