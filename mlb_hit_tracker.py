# ====================== TAB 1: PLAYER STATS ======================
with tab_player:
    st.subheader("🔥 Today's Prop Hot Lists (≥80% Hit Rate - Last 10 Games)")

    today_games = get_todays_games()
    if not today_games:
        st.error("No games found for today.")
        st.stop()

    # Game selector
    game_options = [g["display"] for g in today_games]
    selected_display = st.selectbox("Select a game", options=game_options, key="game_select")
    selected_game = next((g for g in today_games if g["display"] == selected_display), None)

    if selected_game:
        away_abbrev = selected_game["awayAbbrev"]
        home_abbrev = selected_game["homeAbbrev"]

        # === LIVE HOT LISTS ===
        with st.spinner("Computing live hot lists for this game..."):
            away_batters = get_team_active_roster(selected_game["awayId"])
            home_batters = get_team_active_roster(selected_game["homeId"])

            batter_list = []
            for b in away_batters:
                batter_list.append((b["id"], b["fullName"], away_abbrev))
            for b in home_batters:
                batter_list.append((b["id"], b["fullName"], home_abbrev))

            hits_qualifiers = []
            strikeouts_qualifiers = []
            hrr_qualifiers = []

            for player_id, full_name, team_abbrev in batter_list:
                game_splits = get_game_log(player_id)
                if len(game_splits) < 5:
                    continue

                records = []
                for split in game_splits:
                    stat = split.get("stat", {})
                    hits = int(stat.get("hits", 0))
                    runs = int(stat.get("runs", 0))
                    rbi = int(stat.get("rbi", 0))
                    strikeouts = int(stat.get("strikeOuts", 0))
                    combined = hits + runs + rbi

                    records.append({"H": hits, "K": strikeouts, "HRR": combined})

                if not records:
                    continue

                df = pd.DataFrame(records)
                pdata = df.head(10).copy()   # Same as player view
                n_games = len(pdata)

                if n_games < 5:
                    continue

                over_05_h = (pdata["H"] > 0.5).sum() / n_games * 100
                over_15_h = (pdata["H"] > 1.5).sum() / n_games * 100
                over_05_k = (pdata["K"] > 0.5).sum() / n_games * 100
                over_15_k = (pdata["K"] > 1.5).sum() / n_games * 100
                over_15_hrr = (pdata["HRR"] > 1.5).sum() / n_games * 100

                batter_stats = {
                    "player": f"{full_name} ({team_abbrev})",
                    "over_0.5_H": round(over_05_h, 1),
                    "over_1.5_H": round(over_15_h, 1),
                    "over_0.5_K": round(over_05_k, 1),
                    "over_1.5_K": round(over_15_k, 1),
                    "over_1.5_HRR": round(over_15_hrr, 1),
                    "games_considered": n_games
                }

                if over_05_h >= 80 or over_15_h >= 80:
                    hits_qualifiers.append(batter_stats)
                if over_05_k >= 80 or over_15_k >= 80:
                    strikeouts_qualifiers.append(batter_stats)
                if over_15_hrr >= 80:
                    hrr_qualifiers.append(batter_stats)

        # Display the live hot lists
        col1, col2, col3 = st.columns(3)

        with col1:
            with st.expander("Hits Hot List", expanded=True):
                df = pd.DataFrame(hits_qualifiers)
                if not df.empty:
                    df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                    if not df.empty:
                        df_display = df[["player", "over_0.5_H", "over_1.5_H"]].copy()
                        df_display["avg_rate"] = ((df_display["over_0.5_H"] + df_display["over_1.5_H"]) / 2).round(1)
                        st.dataframe(df_display, use_container_width=True, hide_index=True,
                            column_config={
                                "player": st.column_config.TextColumn("Player"),
                                "over_0.5_H": st.column_config.NumberColumn("% >0.5 H", format="%.1f%%"),
                                "over_1.5_H": st.column_config.NumberColumn("% >1.5 H", format="%.1f%%"),
                                "avg_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                            })

        with col2:
            with st.expander("Strikeouts Hot List", expanded=True):
                df = pd.DataFrame(strikeouts_qualifiers)
                if not df.empty:
                    df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                    if not df.empty:
                        df_display = df[["player", "over_0.5_K", "over_1.5_K"]].copy()
                        df_display["avg_rate"] = ((df_display["over_0.5_K"] + df_display["over_1.5_K"]) / 2).round(1)
                        st.dataframe(df_display, use_container_width=True, hide_index=True,
                            column_config={
                                "player": st.column_config.TextColumn("Player"),
                                "over_0.5_K": st.column_config.NumberColumn("% >0.5 K", format="%.1f%%"),
                                "over_1.5_K": st.column_config.NumberColumn("% >1.5 K", format="%.1f%%"),
                                "avg_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                            })

        with col3:
            with st.expander("H + R + RBI Hot List", expanded=True):
                df = pd.DataFrame(hrr_qualifiers)
                if not df.empty:
                    df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                    if not df.empty:
                        st.dataframe(df[["player", "over_1.5_HRR"]], use_container_width=True, hide_index=True,
                            column_config={
                                "player": st.column_config.TextColumn("Player"),
                                "over_1.5_HRR": st.column_config.NumberColumn("% >1.5 HRR", format="%.1f%%"),
                            })

        st.caption(f"✅ Live calculation for **{away_abbrev} @ {home_abbrev}** • Last 10 games per player")
    else:
        st.info("Select a game above to see live hot lists.")

    st.divider()
