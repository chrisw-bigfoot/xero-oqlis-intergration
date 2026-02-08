import pandas as pd
from datetime import datetime


def parse_period_to_date(period_str: str) -> pd.Timestamp | None:
    """
    Convert strings like 'Mar 2025', 'Apr 2025' → datetime.date (first of month)
    Returns None if parsing fails.
    """
    if not isinstance(period_str, str):
        return None
    
    period_str = period_str.strip()
    try:
        dt = datetime.strptime(period_str, "%b %Y")
        return pd.Timestamp(year=dt.year, month=dt.month, day=1)
    except ValueError:
        try:
            dt = datetime.strptime(period_str, "%B %Y")
            return pd.Timestamp(year=dt.year, month=dt.month, day=1)
        except ValueError:
            return None


def transform_budget_summary(
    file_path: str,
    legal_entity: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = True
) -> pd.DataFrame:
    """
    Transforms the 'Budget Summary - Overall Budget' sheet.

    Parameters:
        file_path: Path to the Excel file
        legal_entity: Legal entity identifier/name to include in output
        drop_profit_rows: If True, removes Gross Profit / Net Profit rows
        melt_to_long: If True, returns long format (legal_entity, section, account, period_date, budget_amount)
                      If False, returns wide format (months as columns with legal_entity)

    Returns:
        pandas DataFrame in long or wide format with legal_entity column
    """
    # ── Read raw data ────────────────────────────────────────────────────────────
    df = pd.read_excel(
        file_path,
        sheet_name="Budget Summary - Overall Budget",
        skiprows=5
    )
    df = df.dropna(how="all")

    # Drop the Total column if present
    if "Total" in df.columns:
        df = df.drop(columns=["Total"])

    # Identify period columns (all except Account)
    period_cols = [col for col in df.columns if col != "Account"]

    # ── Process row by row to assign sections and filter ────────────────────────
    processed_rows = []
    current_section = None

    for _, row in df.iterrows():
        if pd.isna(row["Account"]):
            continue

        account = str(row["Account"]).strip()

        # Section header row → only Account filled, rest NaN
        values = row[period_cols]
        if values.isna().all():
            current_section = account
            continue

        # Skip total rows
        if account.lower().startswith("total "):
            current_section = None
            continue

        # Assign section
        section = current_section if current_section else account

        # Build record
        record = {
            "account": account,
            "section": section
        }
        record.update(values.to_dict())
        processed_rows.append(record)

        # Reset after calculated rows like Gross Profit / Net Profit
        if account in {"Gross Profit", "Net Profit"}:
            current_section = None

    if not processed_rows:
        raise ValueError("No valid data rows found after filtering.")

    cleaned_df = pd.DataFrame(processed_rows)

    # ── Wide or Long format ─────────────────────────────────────────────────────
    if melt_to_long:
        # Long format (your original logic)
        df_long = pd.melt(
            cleaned_df,
            id_vars=["account", "section"],
            var_name="period_str",
            value_name="budget_amount"
        )

        # Drop rows without amount
        df_long = df_long.dropna(subset=["budget_amount"])

        # Ensure numeric
        df_long["budget_amount"] = pd.to_numeric(df_long["budget_amount"], errors="coerce")
        df_long = df_long.dropna(subset=["budget_amount"])

        # Handle drop_profit_rows
        if drop_profit_rows:
            mask = df_long['account'].str.lower().str.strip().isin(['net profit', 'gross profit'])
            df_long = df_long[~mask].copy()

        # Parse period strings to dates
        df_long["period_date"] = df_long["period_str"].apply(parse_period_to_date)

        # Drop original string column
        df_long = df_long.drop(columns=["period_str"])

        # Add legal_entity column
        df_long["legal_entity"] = legal_entity

        # Final clean-up and order
        df_long = df_long.reset_index(drop=True)
        df_long = df_long[["legal_entity", "section", "account", "period_date", "budget_amount"]]

        return df_long

    else:
        # Wide format: months as columns
        wide_df = cleaned_df.copy()

        # Handle drop_profit_rows in wide format
        if drop_profit_rows:
            mask = wide_df['account'].str.lower().str.strip().isin(['net profit', 'gross profit'])
            wide_df = wide_df[~mask].copy().reset_index(drop=True)

        # Add legal_entity column
        wide_df["legal_entity"] = legal_entity

        # Reorder: legal_entity, section, account, then period columns
        period_cols_sorted = sorted([c for c in wide_df.columns if c not in ["section", "account", "legal_entity"]])
        wide_df = wide_df[["legal_entity", "section", "account"] + period_cols_sorted]

        return wide_df.reset_index(drop=True)


# file = "files/budget-summary.xlsx"

# # Long format (database/BI friendly)
# df_long = transform_budget_summary(file, drop_profit_rows=False, melt_to_long=True)
# df_long.to_excel("budget_summary_long.xlsx", index=False)

# # Wide format (like other reports)
# df_wide = transform_budget_summary(file, drop_profit_rows=False, melt_to_long=False)
# df_wide.to_excel("budget_summary_wide.xlsx", index=False)