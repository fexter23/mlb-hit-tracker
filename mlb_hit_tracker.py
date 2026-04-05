import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
import json
import os

# ====================== STREAMLIT APP ======================
st.set_page_config(page_title="MLB Batter Stats", page_icon="⚾", layout="wide")
st.title("⚾ MLB Active Batter Recent Game Stats")

tab_player, tab_parlays = st.tabs(["📊 Player Stats", "🎯 Today's Parlay Suggestions"])

# ====================== TAB 1: PLAYER STATS ======================
with tab_player:
    st.subheader("🔥 Today's Prop Hot Lists (≥80% Hit Rate - Last 10 Games)")

    daily_file = "daily_k_props.json"
    today_games = []  # We'll load from sidebar later

    # Game selector
    with st.sidebar:
        st.header("🎮 Game Selection")
        # Simple placeholder - we'll improve once games load
        st.info("Loading today's games...")

    if os.path.exists(daily_file):
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)

            if daily_data.get("date") == datetime.date.today().strftime("%Y-%m-%d"):
                daily_df = pd.DataFrame(daily_data.get("batters", []))

                if not daily_df.empty:
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        with st.expander("Hits Hot List", expanded=False):
                            df1 = daily_df[["player", "over_0.5_H", "over_1.5_H"]].copy()
                            df1["avg_rate"] = ((df1["over_0.5_H"] + df1["over_1.5_H"]) / 2).round(1)
                            st.dataframe(df1, use_container_width=True, hide_index=True,
                                column_config={
                                    "player": st.column_config.TextColumn("Player"),
                                    "over_0.5_H": st.column_config.NumberColumn("% >0.5 H", format="%.1f%%"),
                                    "over_1.5_H": st.column_config.NumberColumn("% >1.5 H", format="%.1f%%"),
                                    "avg_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                                })

                    with col2:
                        with st.expander("Strikeouts Hot List", expanded=False):
                            df2 = daily_df[["player", "over_0.5_K", "over_1.5_K"]].copy()
                            df2["avg_rate"] = ((df2["over_0.5_K"] + df2["over_1.5_K"]) / 2).round(1)
                            st.dataframe(df2, use_container_width=True, hide_index=True,
                                column_config={
                                    "player": st.column_config.TextColumn("Player"),
                                    "over_0.5_K": st.column_config.NumberColumn("% >0.5 K", format="%.1f%%"),
                                    "over_1.5_K": st.column_config.NumberColumn("% >1.5 K", format="%.1f%%"),
                                    "avg_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                                })

                    with col3:
                        with st.expander("H + R + RBI Hot List", expanded=False):
                            df3 = daily_df[["player", "over_1.5_HRR"]].copy()
                            st.dataframe(df3, use_container_width=True, hide_index=True,
                                column_config={
                                    "player": st.column_config.TextColumn("Player"),
                                    "over_1.5_HRR": st.column_config.NumberColumn("% >1.5 HRR", format="%.1f%%"),
                                })

                    st.caption("✅ Updated today • Last 10 games")
                else:
                    st.info("No qualifying batters today.")
            else:
                st.warning("⚠️ Daily props are outdated. Please run `python compute_daily_k_props.py`")
        except Exception as e:
            st.error(f"Could not load daily props: {e}")
    else:
        st.info("👉 Run `python compute_daily_k_props.py` first to generate hot lists.")

    st.divider()

    # Individual Player Analysis (your original code - kept simple)
    with st.sidebar:
        st.header("Individual Player Analysis")
        st.info("Player selection will be added back once we stabilize the app.")

    st.info("👈 Use the sidebar to select a game and player for detailed stats.")

# ====================== TAB 2: PARLAY SUGGESTIONS ======================
with tab_parlays:
    st.subheader("🎯 Today's 3-Leg Parlay Suggestions")

    daily_file = "daily_k_props.json"

    if os.path.exists(daily_file):
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)

            parlay_suggestions = daily_data.get("parlay_suggestions", [])

            if parlay_suggestions:
                for suggestion in parlay_suggestions:
                    st.markdown(f"#### ⚾ {suggestion.get('game', 'Unknown Game')}")

                    if not suggestion.get("legs"):
                        st.warning(suggestion.get("note", "No legs available."))
                    else:
                        avg_rate = suggestion.get("avg_leg_hit_rate", 0)
                        badge_color = "#00ff88" if avg_rate >= 80 else "#ffcc00" if avg_rate >= 65 else "#ff5555"
                        st.markdown(
                            f"<span style='background:{badge_color}; color:#111; font-weight:700; "
                            f"padding:4px 12px; border-radius:12px;'>Avg hit rate: {avg_rate}%</span>",
                            unsafe_allow_html=True
                        )

                        for i, leg in enumerate(suggestion.get("legs", []), 1):
                            rate = leg.get("hit_rate", 0)
                            rate_color = "#00ff88" if rate >= 80 else "#ffcc00" if rate >= 65 else "#ff5555"
                            st.markdown(
                                f"**Leg {i}** — {leg['player']} — {leg['prop']} "
                                f"<span style='color:{rate_color}; font-weight:700;'>{rate}%</span> "
                                f"({leg.get('games_considered', '?')} games)",
                                unsafe_allow_html=True
                            )
                    st.divider()
            else:
                st.info("No parlay suggestions available yet. Run `compute_daily_k_props.py`")
        except Exception as e:
            st.error(f"Could not load parlay suggestions: {e}")
    else:
        st.info("Run `python compute_daily_k_props.py` to generate parlay suggestions.")

st.divider()
st.caption("Active batters only • Current season • Official MLB Stats API")
