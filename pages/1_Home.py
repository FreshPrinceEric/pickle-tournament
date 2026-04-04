import random
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from supabase_client import supabase


# =========================
# Helpers
# =========================
def build_df(rows, cols):
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)


def format_time_12h(raw_time):
    raw = str(raw_time).split(".")[0]
    return datetime.strptime(raw, "%H:%M:%S").strftime("%I:%M %p").lstrip("0")


def parse_session_start(session_date_value, start_time_value):
    raw_time = str(start_time_value).split(".")[0]
    session_date_obj = date.fromisoformat(str(session_date_value))
    session_time_obj = datetime.strptime(raw_time, "%H:%M:%S").time()
    return datetime.combine(session_date_obj, session_time_obj)


def now_phoenix():
    return datetime.now(ZoneInfo("America/Phoenix"))


def get_session():
    rows = supabase.table("sessions").select("*").execute().data
    if not rows:
        return None

    def session_dt(row):
        return parse_session_start(row["session_date"], row["start_time"]).replace(
            tzinfo=ZoneInfo("America/Phoenix")
        )

    now_dt = now_phoenix()
    upcoming = [row for row in rows if session_dt(row) >= now_dt]

    if upcoming:
        upcoming.sort(key=session_dt)
        return upcoming[0]

    rows.sort(key=session_dt, reverse=True)
    return rows[0]


def get_profiles():
    rows = supabase.table("profiles").select("*").execute().data
    return {
        p["id"]: {
            "first_name": (p.get("first_name") or "").strip(),
            "last_name": (p.get("last_name") or "").strip(),
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "phone": p.get("phone"),
            "email": (p.get("email") or "").strip(),
            "about_acknowledged": bool(p.get("about_acknowledged")),
        }
        for p in rows
    }


def get_first_name(user_id, profile_lookup):
    first_name = profile_lookup.get(user_id, {}).get("first_name", "").strip()
    return first_name if first_name else "Unknown"


def get_full_name(user_id, profile_lookup):
    full_name = profile_lookup.get(user_id, {}).get("name", "").strip()
    return full_name if full_name else "Unknown"


def get_active_registered_teams(session_id):
    return (
        supabase.table("registered_teams")
        .select("*")
        .eq("session_id", session_id)
        .eq("active", True)
        .order("created_at")
        .execute()
        .data
    )


def get_registered_team_lookup(session_id):
    rows = (
        supabase.table("registered_teams")
        .select("*")
        .eq("session_id", session_id)
        .execute()
        .data
    )
    return {row["id"]: row for row in rows}


def get_team_name(team_row, profile_lookup):
    p1 = get_first_name(team_row["player_1_id"], profile_lookup)
    p2 = get_first_name(team_row["player_2_id"], profile_lookup)
    return f"{p1} / {p2}"


def get_booked_courts(session_id):
    return (
        supabase.table("booked_courts")
        .select("*")
        .eq("session_id", session_id)
        .order("court_number")
        .execute()
        .data
    )


def get_existing_rounds(session_id):
    return (
        supabase.table("session_rounds")
        .select("*")
        .eq("session_id", session_id)
        .order("round_number")
        .execute()
        .data
    )


def get_matchups_for_round(round_id):
    return (
        supabase.table("matchups")
        .select("*")
        .eq("round_id", round_id)
        .order("court_number")
        .execute()
        .data
    )


def get_all_matchups(session_id):
    return (
        supabase.table("matchups")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
        .data
    )


def get_team_matchups(session_id, team_id):
    as_team_1 = (
        supabase.table("matchups")
        .select("*")
        .eq("session_id", session_id)
        .eq("team_1_id", team_id)
        .execute()
        .data
    )
    as_team_2 = (
        supabase.table("matchups")
        .select("*")
        .eq("session_id", session_id)
        .eq("team_2_id", team_id)
        .execute()
        .data
    )

    seen = set()
    out = []
    for row in as_team_1 + as_team_2:
        if row["id"] not in seen:
            seen.add(row["id"])
            out.append(row)
    return out


def compute_standings(session_id):
    active_teams = get_active_registered_teams(session_id)
    team_lookup = {t["id"]: t for t in active_teams}

    standings = {
        t["id"]: {"team_id": t["id"], "wins": 0, "losses": 0, "played": 0}
        for t in active_teams
    }

    for m in get_all_matchups(session_id):
        if m["status"] != "Finished":
            continue

        t1 = m["team_1_id"]
        t2 = m.get("team_2_id")
        winner = m.get("winner_team_id")

        if t1 in standings:
            standings[t1]["played"] += 1
            if winner == t1:
                standings[t1]["wins"] += 1
            else:
                standings[t1]["losses"] += 1

        if t2 and t2 in standings:
            standings[t2]["played"] += 1
            if winner == t2:
                standings[t2]["wins"] += 1
            else:
                standings[t2]["losses"] += 1

    return standings, team_lookup


def get_played_pairs(session_id):
    played = set()
    for m in get_all_matchups(session_id):
        t1 = m["team_1_id"]
        t2 = m.get("team_2_id")
        if t1 and t2:
            played.add(tuple(sorted((t1, t2))))
    return played


def choose_bye_team(team_ids, session_id):
    bye_history = set()
    for m in get_all_matchups(session_id):
        if m.get("team_2_id") is None:
            bye_history.add(m["team_1_id"])

    for tid in reversed(team_ids):
        if tid not in bye_history:
            return tid
    return team_ids[-1]


def pair_teams_best_effort(team_ids, played_pairs):
    if not team_ids:
        return []

    first = team_ids[0]

    for i in range(1, len(team_ids)):
        second = team_ids[i]
        pair_key = tuple(sorted((first, second)))
        if pair_key not in played_pairs:
            rest = team_ids[1:i] + team_ids[i + 1:]
            return [(first, second)] + pair_teams_best_effort(rest, played_pairs)

    second = team_ids[1]
    rest = team_ids[2:]
    return [(first, second)] + pair_teams_best_effort(rest, played_pairs)


def generate_round(session_id, round_number):
    existing = (
        supabase.table("session_rounds")
        .select("*")
        .eq("session_id", session_id)
        .eq("round_number", round_number)
        .execute()
        .data
    )
    if existing:
        return existing[0]

    active_teams = get_active_registered_teams(session_id)
    if len(active_teams) < 2:
        return None

    round_row = (
        supabase.table("session_rounds")
        .insert({"session_id": session_id, "round_number": round_number})
        .execute()
        .data[0]
    )
    round_id = round_row["id"]

    courts = [row["court_number"] for row in get_booked_courts(session_id)]
    played_pairs = get_played_pairs(session_id)

    if round_number == 1:
        team_ids = [t["id"] for t in active_teams]
        random.shuffle(team_ids)
    else:
        standings, _ = compute_standings(session_id)
        team_ids = [t["id"] for t in active_teams]
        team_ids.sort(
            key=lambda tid: (
                -standings.get(tid, {}).get("wins", 0),
                standings.get(tid, {}).get("losses", 0),
                tid,
            )
        )

    bye_team_id = None
    pairing_pool = team_ids[:]

    if len(pairing_pool) % 2 == 1:
        bye_team_id = choose_bye_team(pairing_pool, session_id)
        pairing_pool.remove(bye_team_id)

    pairs = pair_teams_best_effort(pairing_pool, played_pairs)

    inserts = []
    court_idx = 0

    if bye_team_id is not None:
        inserts.append(
            {
                "session_id": session_id,
                "round_id": round_id,
                "court_number": None,
                "team_1_id": bye_team_id,
                "team_2_id": None,
                "winner_team_id": bye_team_id,
                "status": "Finished",
            }
        )

    for t1, t2 in pairs:
        court_number = courts[court_idx] if court_idx < len(courts) else None
        court_idx += 1

        inserts.append(
            {
                "session_id": session_id,
                "round_id": round_id,
                "court_number": court_number,
                "team_1_id": t1,
                "team_2_id": t2,
                "winner_team_id": None,
                "status": "Pending",
            }
        )

    if inserts:
        supabase.table("matchups").insert(inserts).execute()

    return round_row


def maybe_generate_rounds(session_id, max_rounds):
    rounds = get_existing_rounds(session_id)
    active_teams = get_active_registered_teams(session_id)

    if len(active_teams) < 2:
        return

    if not rounds:
        generate_round(session_id, 1)
        rounds = get_existing_rounds(session_id)

    while rounds:
        current_round = rounds[-1]
        round_matchups = get_matchups_for_round(current_round["id"])

        if not round_matchups:
            break

        all_finished = all(m["status"] == "Finished" for m in round_matchups)
        if not all_finished:
            break

        next_round = current_round["round_number"] + 1
        if next_round > max_rounds:
            break

        if any(r["round_number"] == next_round for r in rounds):
            break

        generate_round(session_id, next_round)
        rounds = get_existing_rounds(session_id)


def promote_accepted_teams(session_id):
    booked_count = len(get_booked_courts(session_id))
    max_teams = booked_count * 2

    registered = get_active_registered_teams(session_id)
    current_registered = len(registered)
    available_slots = max_teams - current_registered

    if available_slots <= 0:
        return

    accepted_approved = (
        supabase.table("pending_teams")
        .select("*")
        .eq("session_id", session_id)
        .eq("request_status", "Accepted")
        .eq("is_paid", True)
        .order("created_at")
        .execute()
        .data
    )

    accepted_count = len(accepted_approved)
    if accepted_count == 0:
        return

    if current_registered % 2 == 1:
        teams_to_promote = min(1, available_slots, accepted_count)
    else:
        teams_to_promote = min(available_slots, accepted_count)
        teams_to_promote = teams_to_promote - (teams_to_promote % 2)

    if teams_to_promote <= 0:
        return

    for team in accepted_approved[:teams_to_promote]:
        supabase.table("registered_teams").insert(
            {
                "session_id": session_id,
                "player_1_id": team["player_1_id"],
                "player_2_id": team["player_2_id"],
                "active": True,
            }
        ).execute()

        (
            supabase.table("pending_teams")
            .delete()
            .eq("id", team["id"])
            .execute()
        )


def get_head_to_head_record(session_id, team_a_id, team_b_id):
    team_a_wins = 0
    team_b_wins = 0

    for m in get_all_matchups(session_id):
        if m["status"] != "Finished":
            continue

        t1 = m["team_1_id"]
        t2 = m.get("team_2_id")
        if t2 is None:
            continue

        if {t1, t2} == {team_a_id, team_b_id}:
            winner = m.get("winner_team_id")
            if winner == team_a_id:
                team_a_wins += 1
            elif winner == team_b_id:
                team_b_wins += 1

    return team_a_wins, team_b_wins


def get_tied_groups_by_record(standings):
    grouped = {}
    for team_id, stats in standings.items():
        key = (stats["wins"], stats["losses"])
        grouped.setdefault(key, []).append(team_id)

    keys_sorted = sorted(grouped.keys(), key=lambda x: (-x[0], x[1]))
    return [(key, grouped[key]) for key in keys_sorted]


def rank_tied_group(session_id, tied_team_ids):
    if len(tied_team_ids) == 1:
        return [tied_team_ids]

    if len(tied_team_ids) == 2:
        team_a = tied_team_ids[0]
        team_b = tied_team_ids[1]

        team_a_wins, team_b_wins = get_head_to_head_record(session_id, team_a, team_b)

        if team_a_wins > team_b_wins:
            return [[team_a], [team_b]]
        if team_b_wins > team_a_wins:
            return [[team_b], [team_a]]

        return [sorted(tied_team_ids)]

    h2h_wins = {team_id: 0 for team_id in tied_team_ids}
    resolved_pairs = 0

    for i in range(len(tied_team_ids)):
        for j in range(i + 1, len(tied_team_ids)):
            team_a = tied_team_ids[i]
            team_b = tied_team_ids[j]

            team_a_wins, team_b_wins = get_head_to_head_record(session_id, team_a, team_b)

            if team_a_wins > team_b_wins:
                h2h_wins[team_a] += 1
                resolved_pairs += 1
            elif team_b_wins > team_a_wins:
                h2h_wins[team_b] += 1
                resolved_pairs += 1

    if resolved_pairs == 0:
        return [sorted(tied_team_ids)]

    buckets = {}
    for team_id, wins in h2h_wins.items():
        buckets.setdefault(wins, []).append(team_id)

    bucket_keys = sorted(buckets.keys(), reverse=True)

    if len(bucket_keys) == 1:
        return [sorted(tied_team_ids)]

    ranked_groups = []
    for key in bucket_keys:
        ranked_groups.append(sorted(buckets[key]))

    return ranked_groups


def build_ranked_leaderboard_rows(session_id, standings, active_team_lookup, profile_lookup):
    ranked_rows = []
    next_rank = 1

    for _, tied_team_ids in get_tied_groups_by_record(standings):
        ranked_groups = rank_tied_group(session_id, tied_team_ids)

        for group in ranked_groups:
            group_rows = []
            for team_id in group:
                team_row = active_team_lookup.get(team_id)
                if not team_row:
                    continue
                stats = standings[team_id]
                group_rows.append(
                    {
                        "Rank": next_rank,
                        "Team": get_team_name(team_row, profile_lookup),
                        "Wins": stats["wins"],
                        "Losses": stats["losses"],
                        "Played": stats["played"],
                    }
                )

            group_rows.sort(key=lambda x: x["Team"])
            ranked_rows.extend(group_rows)
            next_rank += len(group_rows)

    return ranked_rows


def build_matchups_table(round_matchups, team_lookup, profile_lookup):
    rows = []

    for matchup in round_matchups:
        court_label = matchup["court_number"] if matchup["court_number"] else "BYE"
        team_1_name = get_team_name(team_lookup[matchup["team_1_id"]], profile_lookup)

        if matchup.get("team_2_id") is None:
            rows.append({"Court": court_label, "Team": team_1_name, "Result": "W"})
            continue

        team_2_name = get_team_name(team_lookup[matchup["team_2_id"]], profile_lookup)

        if matchup["status"] == "Finished":
            if matchup["winner_team_id"] == matchup["team_1_id"]:
                result_1, result_2 = "W", "L"
            else:
                result_1, result_2 = "L", "W"
        else:
            result_1, result_2 = "", ""

        rows.append({"Court": court_label, "Team": team_1_name, "Result": result_1})
        rows.append({"Court": court_label, "Team": team_2_name, "Result": result_2})

    return build_df(rows, ["Court", "Team", "Result"])


# =========================
# Page setup
# =========================
if not st.session_state.get("authenticated"):
    st.warning("Please log in")
    st.switch_page("app.py")

session = get_session()
if not session:
    st.error("No session found.")
    st.stop()

session_id = session["id"]
user_id = st.session_state.get("user_id")
profile_lookup = get_profiles()

current_user_name = get_full_name(user_id, profile_lookup)
current_user_email = (st.session_state.get("user") or "").strip().lower()
is_admin = current_user_email == "epcepress@gmail.com"

session_date_str = str(session["session_date"])
about_acknowledged = profile_lookup.get(user_id, {}).get("about_acknowledged", False)

now_dt = now_phoenix()
today_str = now_dt.date().isoformat()

session_start_dt = parse_session_start(session["session_date"], session["start_time"]).replace(
    tzinfo=ZoneInfo("America/Phoenix")
)

session_started = now_dt >= session_start_dt
matchups_available = session_started
registration_locked = now_dt >= session_start_dt
max_rounds = int(session.get("number_of_rounds") or 7)

with st.sidebar:
    st.subheader("Profile")
    st.write(current_user_name)

    if st.button("Edit"):
        st.session_state.edit_profile = True
        st.switch_page("pages/2_Create_Account.py")

    if st.button("Logout"):
        import extra_streamlit_components as stx

        cookie_manager = stx.CookieManager()
        cookie_manager.delete("pb_refresh_token")

        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        st.session_state.clear()
        st.switch_page("app.py")

st.title(f"Session: {session_date_str} - {format_time_12h(session['start_time'])}")

nav_options = ["About", "Registration", "Matchups"]
if is_admin:
    nav_options.append("Admin")

default_view = "Registration"
if not about_acknowledged:
    default_view = "About"
elif today_str == session_date_str and session_started:
    default_view = "Matchups"

if "home_view" not in st.session_state or st.session_state["home_view"] not in nav_options:
    st.session_state["home_view"] = default_view

view = st.radio(
    "View",
    nav_options,
    horizontal=True,
    key="home_view",
    label_visibility="collapsed",
)

if not about_acknowledged and view != "About":
    st.warning("Please read and acknowledge the About page before using Registration or Matchups.")
    st.stop()

if about_acknowledged and view == "Matchups" and not matchups_available:
    st.warning("Matchups will be available at the session start time.")
    st.stop()

# =========================
# About view
# =========================
if view == "About":
    st.subheader("About")

    st.markdown("""
    ## Overview
    This app is used to manage session registration, partner pairing, court assignments, and a Swiss-system tournament format.

    ---

    ## Registration

    ### Registering
    - Click **Register**
    - Select a partner or choose **Looking for a partner**
    - Submit your registration

    ### Partner Requests
    - If you select a partner, a request is sent to them
    - The partner must **accept** the request
    - Once accepted, your team becomes eligible for registration

    ### Looking for a Partner
    - If you register without a partner, your name will appear in:
      **Players Looking for a Partner**
    - Other players can choose you as a partner

    ---

    ## Court Booking

    - If you have booked a court during the session time, you can indicate it using **Add Court**
    - Select the court number you have reserved
    - Courts determine how many teams can be registered:
      - Each court supports **2 teams**
    - If you clear your booking, capacity may decrease

    ---

    ## Promotion to Registered Teams

    A team moves from **Pending** to **Registered** only when:

    1. The partner request is **Accepted**
    2. The team is marked as **Approved**
    3. There is available court capacity
    4. Team counts follow pairing rules (no odd promotions unless necessary)

    Once registered, teams remain registered for the session.

    ---

    ## Tournament Format

    ### Game Rules
    - Games are played to **11 points**
    - Must win by **2 points**
    - Teams **switch sides at 7 points**

    ### Starting Choices
    - A random Team 1 is selected
    - Team 1 chooses:
      - Serve, Receive, OR Side
    - Team 2 then chooses the remaining option

    Examples:
    - If Team 1 chooses **Serve**, Team 2 chooses **Side**
    - If Team 1 chooses **Side**, Team 2 chooses **Serve or Receive**

    ---

    ## Match Reporting

    - Each match appears at the top of your screen when it is your turn to play
    - Either team can submit the result
    - The **first submission is final**

    ---

    ## Swiss-System Format

    This tournament uses a **Swiss-system** format:

    - Teams are paired each round based on their performance
    - Teams with similar records play each other
    - You will not be eliminated after a loss
    - Each round adjusts matchups dynamically

    ### Round Structure
    - Round 1 is random
    - Later rounds group teams by:
      - Number of wins
    - Pairings attempt to avoid repeat matchups when possible

    ### Byes
    - If there is an odd number of teams:
      - One team receives a **bye**
      - A bye counts as a **win**

    ---

    ## Determining the Winner

    ### Primary Ranking
    - Teams are ranked by:
      1. **Total Wins**
      2. **Total Losses**

    ### Tie Breaker Rules

    If two teams are tied:
    - The better combined **head-to-head record** wins

    If the head-to-head record is tied:
    - The teams remain tied

    If three or more teams are tied:
    - The app compares combined head-to-head results within the tied group
    - If that still does not break the tie, the teams remain tied

    ---

    ## Expectations

    - Report results promptly after matches
    - Be ready when your match is assigned
    - Respect court assignments and other players

    ---

    ## Confirmation

    Please confirm that you have read and understand how the system works before proceeding.
    """)

    ack_checked = st.checkbox(
        "I have read and understand the information above.",
        value=about_acknowledged,
        disabled=about_acknowledged,
    )

    if ack_checked and not about_acknowledged:
        (
            supabase.table("profiles")
            .update({"about_acknowledged": True})
            .eq("id", user_id)
            .execute()
        )

        st.session_state.pop("home_view", None)
        st.rerun()

# =========================
# Registration view
# =========================
elif view == "Registration":
    promote_accepted_teams(session_id)

    if registration_locked:
        st.warning("Registration is closed. The session has started.")

    courts = get_booked_courts(session_id)
    booked_numbers = {r["court_number"] for r in courts}
    available = [i for i in range(1, 17) if i not in booked_numbers]

    st.session_state.setdefault("show_register", False)
    st.session_state.setdefault("show_add_court", False)

    if registration_locked:
        st.session_state["show_register"] = False
        st.session_state["show_add_court"] = False

    action_col1, action_col2, action_col3, action_col4 = st.columns(4)

    if action_col1.button("Register", use_container_width=True, disabled=registration_locked):
        st.session_state["show_register"] = True
        st.session_state["show_add_court"] = False
        st.rerun()

    if action_col2.button("Add Court", use_container_width=True, disabled=registration_locked):
        st.session_state["show_add_court"] = True
        st.session_state["show_register"] = False
        st.rerun()

    if action_col3.button("Clear Bookings", use_container_width=True, disabled=registration_locked):
        if registration_locked:
            st.error("Registration is closed.")
            st.stop()

        (
            supabase.table("booked_courts")
            .delete()
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        promote_accepted_teams(session_id)
        st.rerun()

    if action_col4.button("Withdraw", use_container_width=True, disabled=registration_locked):
        if registration_locked:
            st.error("Registration is closed.")
            st.stop()

        (
            supabase.table("players_looking_for_partner")
            .delete()
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .execute()
        )

        (
            supabase.table("pending_teams")
            .delete()
            .eq("session_id", session_id)
            .or_(f"player_1_id.eq.{user_id},player_2_id.eq.{user_id}")
            .execute()
        )

        st.session_state["show_register"] = False
        st.session_state["show_add_court"] = False
        promote_accepted_teams(session_id)
        st.rerun()

    if st.session_state["show_register"] and not registration_locked:
        registered_rows = get_active_registered_teams(session_id)

        accepted_rows = (
            supabase.table("pending_teams")
            .select("*")
            .eq("session_id", session_id)
            .eq("request_status", "Accepted")
            .execute()
            .data
        )

        unavailable_ids = set()

        for r in registered_rows:
            unavailable_ids.add(r["player_1_id"])
            unavailable_ids.add(r["player_2_id"])

        for r in accepted_rows:
            unavailable_ids.add(r["player_1_id"])
            unavailable_ids.add(r["player_2_id"])

        eligible_partners = {
            pid: get_full_name(pid, profile_lookup)
            for pid, v in profile_lookup.items()
            if pid != user_id and pid not in unavailable_ids and v["name"]
        }

        options = ["No partner / Looking for partner"] + sorted(eligible_partners.values())

        st.subheader("Register")
        selected_name = st.selectbox("Partner", options)

        if st.button("Submit Registration", disabled=registration_locked):
            if registration_locked:
                st.error("Registration is closed.")
                st.stop()

            (
                supabase.table("players_looking_for_partner")
                .delete()
                .eq("session_id", session_id)
                .eq("user_id", user_id)
                .execute()
            )

            if selected_name == "No partner / Looking for partner":
                supabase.table("players_looking_for_partner").insert(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                    }
                ).execute()
            else:
                partner_id = next(
                    pid for pid, name in eligible_partners.items()
                    if name == selected_name
                )

                (
                    supabase.table("pending_teams")
                    .delete()
                    .eq("session_id", session_id)
                    .eq("player_1_id", user_id)
                    .execute()
                )

                reverse_request = (
                    supabase.table("pending_teams")
                    .select("*")
                    .eq("session_id", session_id)
                    .eq("player_1_id", partner_id)
                    .eq("player_2_id", user_id)
                    .execute()
                    .data
                )

                if reverse_request:
                    reverse_id = reverse_request[0]["id"]

                    (
                        supabase.table("pending_teams")
                        .update({"request_status": "Accepted"})
                        .eq("id", reverse_id)
                        .execute()
                    )

                    (
                        supabase.table("players_looking_for_partner")
                        .delete()
                        .eq("session_id", session_id)
                        .eq("user_id", partner_id)
                        .execute()
                    )
                else:
                    supabase.table("pending_teams").insert(
                        {
                            "session_id": session_id,
                            "player_1_id": user_id,
                            "player_2_id": partner_id,
                            "request_status": "Pending",
                            "is_paid": False,
                        }
                    ).execute()

            promote_accepted_teams(session_id)
            st.session_state["show_register"] = False
            st.rerun()

    if st.session_state["show_add_court"] and not registration_locked:
        st.subheader("Add Court")

        if available:
            selected_court = st.selectbox("Court", available)

            if st.button("Submit Court", disabled=registration_locked):
                if registration_locked:
                    st.error("Registration is closed.")
                    st.stop()

                supabase.table("booked_courts").insert(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "court_number": selected_court,
                    }
                ).execute()

                promote_accepted_teams(session_id)
                st.rerun()
        else:
            st.info("No courts available.")

    incoming_requests = (
        supabase.table("pending_teams")
        .select("*")
        .eq("session_id", session_id)
        .eq("player_2_id", user_id)
        .eq("request_status", "Pending")
        .execute()
        .data
    )

    if incoming_requests:
        st.subheader("Partner Requests")

        for req in incoming_requests:
            requester = get_full_name(req["player_1_id"], profile_lookup)
            st.write(f"{requester} requested you")

            col1, col2 = st.columns(2)

            if col1.button("Accept", key=f"accept_{req['id']}", disabled=registration_locked):
                if registration_locked:
                    st.error("Registration is closed.")
                    st.stop()

                (
                    supabase.table("pending_teams")
                    .update({"request_status": "Accepted"})
                    .eq("id", req["id"])
                    .execute()
                )

                other_requests = (
                    supabase.table("pending_teams")
                    .select("id")
                    .eq("session_id", session_id)
                    .eq("player_2_id", user_id)
                    .eq("request_status", "Pending")
                    .neq("id", req["id"])
                    .execute()
                    .data
                )

                for other in other_requests:
                    (
                        supabase.table("pending_teams")
                        .delete()
                        .eq("id", other["id"])
                        .execute()
                    )

                (
                    supabase.table("players_looking_for_partner")
                    .delete()
                    .eq("session_id", session_id)
                    .eq("user_id", user_id)
                    .execute()
                )

                (
                    supabase.table("players_looking_for_partner")
                    .delete()
                    .eq("session_id", session_id)
                    .eq("user_id", req["player_1_id"])
                    .execute()
                )

                st.rerun()

            if col2.button("Reject", key=f"reject_{req['id']}", disabled=registration_locked):
                if registration_locked:
                    st.error("Registration is closed.")
                    st.stop()

                (
                    supabase.table("pending_teams")
                    .delete()
                    .eq("id", req["id"])
                    .execute()
                )
                st.rerun()

    looking = (
        supabase.table("players_looking_for_partner")
        .select("*")
        .eq("session_id", session_id)
        .execute()
        .data
    )

    st.subheader("Players Looking for a Partner")
    st.table(
        build_df(
            [
                {
                    "Player": get_full_name(r["user_id"], profile_lookup),
                    "Phone": profile_lookup[r["user_id"]]["phone"],
                }
                for r in looking
            ],
            ["Player", "Phone"],
        )
    )

    pending = (
        supabase.table("pending_teams")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
        .data
    )

    if is_admin:
        accepted_unapproved = [
            row for row in pending
            if row["request_status"] == "Accepted" and not row.get("is_paid", False)
        ]

        if accepted_unapproved:
            team_label_to_id = {}
            team_labels = []

            for row in accepted_unapproved:
                label = f"{get_full_name(row['player_1_id'], profile_lookup)} / {get_full_name(row['player_2_id'], profile_lookup)}"
                team_labels.append(label)
                team_label_to_id[label] = row["id"]

            selected_unapproved_team = st.selectbox(
                "Accepted unapproved team",
                ["Select team"] + team_labels,
            )

            if st.button("Approve Team", disabled=registration_locked):
                if registration_locked:
                    st.error("Registration is closed.")
                    st.stop()

                if selected_unapproved_team != "Select team":
                    (
                        supabase.table("pending_teams")
                        .update({"is_paid": True})
                        .eq("id", team_label_to_id[selected_unapproved_team])
                        .execute()
                    )
                    promote_accepted_teams(session_id)
                    st.rerun()

    st.subheader("Pending Teams")
    st.table(
        build_df(
            [
                {
                    "Player 1": get_full_name(r["player_1_id"], profile_lookup),
                    "Player 2": get_full_name(r["player_2_id"], profile_lookup),
                    "Request": r["request_status"],
                }
                for r in pending
            ],
            ["Player 1", "Player 2", "Request"],
        )
    )

    registered = get_active_registered_teams(session_id)

    st.subheader("Registered Teams")
    st.table(
        build_df(
            [
                {
                    "Player 1": get_full_name(r["player_1_id"], profile_lookup),
                    "Player 2": get_full_name(r["player_2_id"], profile_lookup),
                }
                for r in registered
            ],
            ["Player 1", "Player 2"],
        )
    )

    courts = get_booked_courts(session_id)

    st.subheader("Booked Courts")
    st.table(
        build_df(
            [
                {
                    "Court": r["court_number"],
                    "Player": get_full_name(r["user_id"], profile_lookup),
                }
                for r in courts
            ],
            ["Court", "Player"],
        )
    )

# =========================
# Matchups view
# =========================
elif view == "Matchups":
    maybe_generate_rounds(session_id, max_rounds)

    rounds = get_existing_rounds(session_id)
    if not rounds:
        st.info("No rounds exist yet.")
        st.stop()

    current_round_number = max(r["round_number"] for r in rounds)
    round_options = [r["round_number"] for r in rounds]

    standings, active_team_lookup = compute_standings(session_id)
    team_lookup = get_registered_team_lookup(session_id)

    current_round = next(r for r in rounds if r["round_number"] == current_round_number)
    current_round_matchups = get_matchups_for_round(current_round["id"])

    user_team_rows = (
        supabase.table("registered_teams")
        .select("*")
        .eq("session_id", session_id)
        .eq("active", True)
        .or_(f"player_1_id.eq.{user_id},player_2_id.eq.{user_id}")
        .execute()
        .data
    )
    user_team_ids = {row["id"] for row in user_team_rows}

    your_match = None
    for m in current_round_matchups:
        if m["status"] != "Pending":
            continue
        if m["team_1_id"] in user_team_ids or m.get("team_2_id") in user_team_ids:
            your_match = m
            break

    if your_match:
        st.subheader("Your Match")

        team_1_name = get_team_name(team_lookup[your_match["team_1_id"]], profile_lookup)
        team_2_name = get_team_name(team_lookup[your_match["team_2_id"]], profile_lookup)
        court_text = f"Court {your_match['court_number']}" if your_match["court_number"] else "No Court Assigned"

        with st.container(border=True):
            st.write(court_text)
            st.write(team_1_name)
            st.write("vs")
            st.write(team_2_name)

            col1, col2 = st.columns(2)

            if col1.button("Team 1 Wins", key=f"team1_win_{your_match['id']}"):
                fresh = (
                    supabase.table("matchups")
                    .select("*")
                    .eq("id", your_match["id"])
                    .execute()
                    .data[0]
                )
                if fresh["status"] == "Pending":
                    (
                        supabase.table("matchups")
                        .update(
                            {
                                "winner_team_id": fresh["team_1_id"],
                                "status": "Finished",
                            }
                        )
                        .eq("id", fresh["id"])
                        .execute()
                    )
                    maybe_generate_rounds(session_id, max_rounds)
                    st.rerun()

            if col2.button("Team 2 Wins", key=f"team2_win_{your_match['id']}"):
                fresh = (
                    supabase.table("matchups")
                    .select("*")
                    .eq("id", your_match["id"])
                    .execute()
                    .data[0]
                )
                if fresh["status"] == "Pending":
                    (
                        supabase.table("matchups")
                        .update(
                            {
                                "winner_team_id": fresh["team_2_id"],
                                "status": "Finished",
                            }
                        )
                        .eq("id", fresh["id"])
                        .execute()
                    )
                    maybe_generate_rounds(session_id, max_rounds)
                    st.rerun()

    st.subheader("Leaderboard")

    leaderboard_rows = build_ranked_leaderboard_rows(
        session_id,
        standings,
        active_team_lookup,
        profile_lookup,
    )
    st.table(build_df(leaderboard_rows, ["Rank", "Team", "Wins", "Losses", "Played"]))

    selected_round_number = st.radio(
        "Round",
        round_options,
        index=round_options.index(current_round_number),
        horizontal=True,
    )

    selected_round = next(r for r in rounds if r["round_number"] == selected_round_number)
    round_matchups = get_matchups_for_round(selected_round["id"])

    if is_admin and round_matchups:
        correction_options = []
        correction_lookup = {}

        for m in round_matchups:
            if m.get("team_2_id") is None:
                continue

            label = f"Court {m['court_number'] if m['court_number'] else '-'}: {get_team_name(team_lookup[m['team_1_id']], profile_lookup)} vs {get_team_name(team_lookup[m['team_2_id']], profile_lookup)}"
            correction_options.append(label)
            correction_lookup[label] = m

        if correction_options:
            st.subheader("Admin Result Correction")
            selected_match_label = st.selectbox("Match to correct", correction_options)
            selected_match = correction_lookup[selected_match_label]

            col1, col2 = st.columns(2)
            if col1.button("Set Team 1 Win"):
                (
                    supabase.table("matchups")
                    .update(
                        {
                            "winner_team_id": selected_match["team_1_id"],
                            "status": "Finished",
                        }
                    )
                    .eq("id", selected_match["id"])
                    .execute()
                )
                maybe_generate_rounds(session_id, max_rounds)
                st.rerun()

            if col2.button("Set Team 2 Win"):
                (
                    supabase.table("matchups")
                    .update(
                        {
                            "winner_team_id": selected_match["team_2_id"],
                            "status": "Finished",
                        }
                    )
                    .eq("id", selected_match["id"])
                    .execute()
                )
                maybe_generate_rounds(session_id, max_rounds)
                st.rerun()

    st.subheader("Matchups")
    st.table(build_matchups_table(round_matchups, team_lookup, profile_lookup))

# =========================
# Admin view
# =========================
elif view == "Admin":
    st.subheader("Admin")

    st.markdown("### Current Session")
    st.write(f"Date: {session_date_str}")
    st.write(f"Start Time: {format_time_12h(session['start_time'])}")
    st.write(f"Rounds: {max_rounds}")

    st.markdown("### Clear Current Session")
    st.caption("This clears registration, courts, rounds, and matchups for the current session.")

    if st.button("Clear Session", type="primary"):
        (
            supabase.table("matchups")
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

        (
            supabase.table("session_rounds")
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

        (
            supabase.table("registered_teams")
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

        (
            supabase.table("pending_teams")
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

        (
            supabase.table("players_looking_for_partner")
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

        (
            supabase.table("booked_courts")
            .delete()
            .eq("session_id", session_id)
            .execute()
        )

        st.session_state["show_register"] = False
        st.session_state["show_add_court"] = False
        st.success("Current session cleared.")
        st.rerun()

    st.markdown("### Create New Session")

    with st.form("create_new_session_form"):
        new_session_date = st.date_input("Session date")

        time_col1, time_col2, time_col3 = st.columns(3)
        new_session_hour = time_col1.selectbox("Hour", list(range(1, 13)), index=5)
        new_session_minute = time_col2.selectbox("Minute", ["00", "30"], index=0)
        new_session_ampm = time_col3.selectbox("AM/PM", ["AM", "PM"], index=1)

        new_session_rounds = st.number_input(
            "Number of rounds",
            min_value=1,
            max_value=20,
            value=7,
            step=1,
        )

        create_session = st.form_submit_button("Create New Session")

    if create_session:
        hour_24 = new_session_hour % 12
        if new_session_ampm == "PM":
            hour_24 += 12

        start_time_24 = f"{hour_24:02d}:{int(new_session_minute):02d}:00"

        (
            supabase.table("sessions")
            .insert(
                {
                    "session_date": new_session_date.isoformat(),
                    "start_time": start_time_24,
                    "number_of_rounds": int(new_session_rounds),
                }
            )
            .execute()
        )

        st.success("New session created.")
        st.rerun()