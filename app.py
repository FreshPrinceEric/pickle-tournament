import streamlit as st
import extra_streamlit_components as stx

from supabase_client import supabase

COOKIE_NAME = "pb_refresh_token"


@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()


def set_auth_state(session):
    st.session_state.authenticated = True
    st.session_state.user = session.user.email
    st.session_state.user_id = session.user.id


def clear_auth_state():
    st.session_state.pop("authenticated", None)
    st.session_state.pop("user", None)
    st.session_state.pop("user_id", None)


def try_restore_session():
    if st.session_state.get("authenticated"):
        return

    cookie_manager = get_cookie_manager()
    refresh_token = cookie_manager.get(COOKIE_NAME)

    if not refresh_token:
        return

    try:
        response = supabase.auth.refresh_session(refresh_token)
        if response.session is not None and response.user is not None:
            set_auth_state(response)
            cookie_manager.set(
                COOKIE_NAME,
                response.session.refresh_token,
                max_age=60 * 60 * 24 * 30,
            )
            st.rerun()
        else:
            cookie_manager.delete(COOKIE_NAME)
            clear_auth_state()
    except Exception:
        cookie_manager.delete(COOKIE_NAME)
        clear_auth_state()


try_restore_session()

if st.session_state.get("authenticated"):
    st.switch_page("pages/1_Home.py")

st.title("Login")

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
                set_auth_state(response)

                cookie_manager = get_cookie_manager()
                cookie_manager.set(
                    COOKIE_NAME,
                    response.session.refresh_token,
                    max_age=60 * 60 * 24 * 30,
                )

                st.switch_page("pages/1_Home.py")
            else:
                st.error("Invalid email or password.")
        except Exception:
            st.error("Invalid email or password.")

if st.button("Create Account"):
    st.switch_page("pages/2_Create_Account.py")