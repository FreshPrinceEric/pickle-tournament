import streamlit as st
from supabase_client import supabase

st.title("Login")

email = st.text_input("Email")
password = st.text_input("Password", type="password")

if st.button("Login"):
    if not email or not password:
        st.error("Email and password are required.")
    else:
        try:
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if response.user is not None:
                st.session_state.authenticated = True
                st.session_state.user = response.user.email
                st.session_state.user_id = response.user.id
                st.switch_page("pages/1_Home.py")
            else:
                st.error("Invalid email or password.")

        except Exception:
            st.error("Invalid email or password.")

if st.button("Create Account"):
    st.switch_page("pages/2_Create_Account.py")