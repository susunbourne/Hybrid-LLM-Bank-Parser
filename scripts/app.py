"""
Streamlit App for Bank Statement Analysis
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from collections import Counter
import os
import tempfile
import requests

from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)


from classifier import ClassificationResult

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Budget Manager",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stMetric {
        background: #f7f7f5;
        border: 1px solid #e8e8e4;
        border-radius: 8px;
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Initialize classifier once ────────────────────────────────────────────────


if "df" not in st.session_state:
    st.session_state.df = None

if "classification_stats" not in st.session_state:
    st.session_state.classification_stats = None

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    bank_choice = st.radio(
        "Bank type",
        ["Bank of America", "Bank of America Credit Card"]
    )

    st.divider()
    st.markdown(
        "<small style='color:#999'>All processing happens locally.<br>"
        "No data is stored externally.</small>",
        unsafe_allow_html=True
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📤 Upload & Classify", "📊 Analysis"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Upload & Classify
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## Upload Bank Statements")
    st.markdown("Upload one or more PDF statements. Transactions will be extracted and classified automatically.")

    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type="pdf",
        accept_multiple_files=True,
    )

    if st.button("▶ Process & Classify", type="primary", use_container_width=True):
        if not uploaded_files:
            st.error("Please upload at least one PDF file.")
        else:
            try:
                config, _, output_path = get_bank_config(bank_choice)

                all_dfs = []
                all_results = []
                progress = st.progress(0)
                status_area = st.empty()

                for i, uploaded_file in enumerate(uploaded_files):
                    status_area.write(f"Processing **{uploaded_file.name}**...")

                    # Save to temp file
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(uploaded_file.getbuffer())
                        tmp_path = Path(tmp.name)

                    processor = StatementProcessor(tmp_path, config)
                    df = processor.process()
                    tmp_path.unlink(missing_ok=True)

                    if df.empty:
                        st.warning(f"No transactions found in {uploaded_file.name}.")
                        continue

                    # Classify
                    results: list[ClassificationResult] = []
                    classify_progress = st.progress(0, text="Classifying transactions...")
                    for j, (_, row) in enumerate(df.iterrows()):
                        response = requests.post(
                            "https://hybrid-llm-bank-parser.onrender.com/api/classify",
                            json={"description": row["description"]}
                        )
                        result_dict = response.json()
                        
                        # convert to ClassificationResult object
                        result = ClassificationResult(
                            category_main=result_dict["category_main"],
                            category_sub=result_dict.get("category_sub"),
                            classification_method=result_dict.get("classification_method")
                        )
                        results.append(result)
                        classify_progress.progress(
                            (j + 1) / len(df),
                            text=f"Classifying {j + 1}/{len(df)}"
                        )
                    classify_progress.empty()

                    df["category_main"]         = [r.category_main for r in results]
                    df["category_sub"]          = [r.category_sub or "" for r in results]
                    df["classification_method"] = [r.classification_method or "" for r in results]

                    all_dfs.append(df)
                    all_results.extend(results)
                    progress.progress((i + 1) / len(uploaded_files))

                status_area.empty()
                progress.empty()

                if not all_dfs:
                    st.error("No transactions found in any of the uploaded files.")
                else:
                    combined = pd.concat(all_dfs, ignore_index=True).sort_values("transaction_date")
                    st.session_state.df = combined

                    # Classification stats
                    success   = [r for r in all_results if r.category_main not in ("Empty", "Nonsense", "Uncertain")]
                    failed    = [r for r in all_results if r.category_main in ("Empty", "Nonsense")]
                    uncertain = [r for r in all_results if r.category_main == "Uncertain"]
                    st.session_state.classification_stats = {
                        "total":         len(all_results),
                        "success":       len(success),
                        "failed":        len(failed),
                        "uncertain":     len(uncertain),
                        "method_counts": dict(Counter(r.classification_method for r in success))
                    }

                    st.success(f"✅ Processed **{len(combined)}** transactions from {len(all_dfs)} file(s).")

                    stats = st.session_state.classification_stats
                    c1, c2, c3 = st.columns(3)
                    c1.metric("✅ Classified", stats["success"])
                    c2.metric("⚠️ Uncertain",  stats["uncertain"])
                    c3.metric("❌ Failed",      stats["failed"])

                    st.markdown("**Method breakdown:**")
                    for method, count in stats["method_counts"].items():
                        st.markdown(f"- `{method}`: {count}")

                    st.divider()
                    st.markdown("### Preview")
                    st.dataframe(combined.head(20), use_container_width=True, hide_index=True)

                    csv = combined.to_csv(index=False)
                    st.download_button(
                        "⬇️ Download CSV",
                        data=csv,
                        file_name="transactions.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

            except Exception as e:
                st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Analysis
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## Expense Analysis")

    if st.session_state.df is None:
        st.info("Upload and process statements in the first tab to see analysis here.")
    else:
        df = st.session_state.df

        income_df  = df[df["amount"] > 0].copy()
        expense_df = df[df["amount"] < 0].copy()
        expense_df["amount_abs"] = expense_df["amount"].abs()

        total_income  = income_df["amount"].sum()
        total_expense = expense_df["amount"].sum()
        net           = total_income + total_expense

        # Summary metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💵 Total Income",  f"${total_income:,.2f}")
        c2.metric("💸 Total Expense", f"${abs(total_expense):,.2f}")
        c3.metric("📊 Net",           f"${net:,.2f}")
        c4.metric("📝 Transactions",  len(df))

        st.divider()

        # Monthly income vs expense
        st.markdown("### Monthly Income vs Expense")
        df["year_month"]    = df["transaction_date"].dt.to_period("M").astype(str)
        monthly_income  = df[df["amount"] > 0].groupby("year_month")["amount"].sum()
        monthly_expense = df[df["amount"] < 0].groupby("year_month")["amount"].sum().abs()

        fig_monthly = go.Figure()
        fig_monthly.add_trace(go.Bar(
            x=monthly_income.index.tolist(),
            y=monthly_income.values,
            name="Income",
            marker_color="#2ecc71"
        ))
        fig_monthly.add_trace(go.Bar(
            x=monthly_expense.index.tolist(),
            y=monthly_expense.values,
            name="Expense",
            marker_color="#e74c3c"
        ))
        fig_monthly.update_layout(
            barmode="group",
            xaxis_title="Month",
            yaxis_title="Amount ($)",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.1),
            margin=dict(t=20)
        )
        st.plotly_chart(fig_monthly, use_container_width=True)

        st.divider()

        # Category breakdown
        st.markdown("### Expense Breakdown by Category")
        col1, col2 = st.columns([1, 1])

        category_totals = (
            expense_df.groupby("category_main")["amount_abs"]
            .sum()
            .sort_values(ascending=False)
        )

        with col1:
            fig_pie = px.pie(
                values=category_totals.values,
                names=category_totals.index,
                hole=0.35,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            category_table = pd.DataFrame({
                "Category":      category_totals.index,
                "Amount ($)":    [f"${v:,.2f}" for v in category_totals.values],
                "% of Expenses": [
                    f"{v / abs(total_expense) * 100:.1f}%"
                    for v in category_totals.values
                ]
            })
            st.dataframe(category_table, use_container_width=True, hide_index=True)

        st.divider()

        # Classification method breakdown
        st.markdown("### Classification Method Breakdown")
        method_counts = df["classification_method"].value_counts()
        fig_methods = px.bar(
            x=method_counts.index,
            y=method_counts.values,
            labels={"x": "Method", "y": "Count"},
            color=method_counts.index,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_methods.update_layout(showlegend=False, margin=dict(t=10))
        st.plotly_chart(fig_methods, use_container_width=True)

        st.divider()

        # Raw data table
        st.markdown("### All Transactions")
        view_mode = st.radio("Show", ["All", "Income only", "Expenses only"], horizontal=True)
        if view_mode == "Income only":
            display_df = income_df
        elif view_mode == "Expenses only":
            display_df = expense_df
        else:
            display_df = df

        st.dataframe(
            display_df[[
                "transaction_date", "description", "amount",
                "category_main", "category_sub", "classification_method"
            ]],
            use_container_width=True,
            hide_index=True
        )