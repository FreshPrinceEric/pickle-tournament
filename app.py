import time
import streamlit as st
import extra_streamlit_components as stx

from supabase_client import supabase

COOKIE_NAME = "pb_refresh_token"
LOGOUT_COOKIE = "pb_logged_out"


def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager()
    return st.session_state["cookie_manager"]


def set_auth_state(user):
    st.session_state.authenticated = True
    st.session_state.user = user.email
    st.session_state.user_id = user.id


def clear_auth_state():
    st.session_state.pop("authenticated", None)
    st.session_state.pop("user", None)
    st.session_state.pop("user_id", None)


def perform_logout_if_requested():
    if not st.session_state.get("perform_logout"):
        return

    cookie_manager = get_cookie_manager()

    clear_auth_state()
    st.session_state["logged_out"] = True

    cookie_manager.set(
        LOGOUT_COOKIE,
        "1",
        max_age=60 * 60 * 24 * 7,
        key="logout_set_marker",
    )
    cookie_manager.set(
        COOKIE_NAME,
        "",
        max_age=0,
        key="logout_clear_refresh",
    )

    st.session_state.pop("perform_logout", None)
    st.rerun()


def try_restore_session():
    if st.session_state.get("authenticated"):
        return

    if st.session_state.get("logged_out"):
        clear_auth_state()
        return

    cookie_manager = get_cookie_manager()

    time.sleep(0.2)
    cookies = cookie_manager.get_all(key="restore_get_all")

    if cookies.get(LOGOUT_COOKIE) == "1":
        clear_auth_state()
        st.session_state["logged_out"] = True
        return

    refresh_token = cookies.get(COOKIE_NAME)

    if not refresh_token:
        clear_auth_state()
        return

    try:
        response = supabase.auth.refresh_session(refresh_token)

        if response.session is not None and response.user is not None:
            set_auth_state(response.user)

            cookie_manager.set(
                COOKIE_NAME,
                response.session.refresh_token,
                max_age=60 * 60 * 24 * 30,
                key="restore_set_refresh",
            )

            st.rerun()
        else:
            cookie_manager.set(
                COOKIE_NAME,
                "",
                max_age=0,
                key="restore_clear_refresh_no_session",
            )
            clear_auth_state()
    except Exception:
        cookie_manager.set(
            COOKIE_NAME,
            "",
            max_age=0,
            key="restore_clear_refresh_exception",
        )
        clear_auth_state()


st.title("Login")

cookie_manager = get_cookie_manager()
perform_logout_if_requested()
try_restore_session()

if st.session_state.get("authenticated"):
    st.switch_page("pages/1_Home.py")

email = st.text_input("Email")
password = st.text_input("Password", type="password")

if st.button("Login"):
    if not email or not password:
        st.error("Email and password are required.")
    else:
        try:
            response = supabase.auth.sign_in_with_password(
                {
                    "email": email,
                    "password": password,
                }
            )

            if response.session is not None and response.user is not None:
                set_auth_state(response.user)
                st.session_state.pop("logged_out", None)

                cookie_manager.set(
                    COOKIE_NAME,
                    response.session.refresh_token,
                    max_age=60 * 60 * 24 * 30,
                    key="login_set_refresh",
                )
                cookie_manager.set(
                    LOGOUT_COOKIE,
                    "",
                    max_age=0,
                    key="login_clear_logout_marker",
                )

                time.sleep(0.2)
                st.switch_page("pages/1_Home.py")
            else:
                st.error("Invalid email or password.")
        except Exception:
            st.error("Invalid email or password.")

if st.button("Create Account"):
    st.switch_page("pages/2_Create_Account.py")