import streamlit as st
from supabase_client import supabase

if not st.session_state.get("authenticated"):
    mode = "create"
else:
    mode = "edit" if st.session_state.get("edit_profile") else "create"

st.title("Edit Profile" if mode == "edit" else "Create Account")

if mode == "edit":
    user_id = st.session_state.get("user_id")

    profile_rows = (
        supabase.table("profiles")
        .select("email, first_name, last_name, phone")
        .eq("id", user_id)
        .execute()
        .data
    )

    if not profile_rows:
        st.error("Profile not found.")
        st.stop()

    profile = profile_rows[0]

    email = st.text_input("Email", value=profile.get("email", ""), disabled=True)
    first_name = st.text_input("First Name", value=profile.get("first_name", ""), disabled=True)
    last_name = st.text_input("Last Name", value=profile.get("last_name", ""), disabled=True)
    phone = st.text_input("Phone", value=profile.get("phone", "") or "")

    if st.button("Save"):
        try:
            (
                supabase.table("profiles")
                .update({"phone": phone if phone else None})
                .eq("id", user_id)
                .execute()
            )

            st.session_state.edit_profile = False
            st.switch_page("pages/1_Home.py")

        except Exception:
            st.error("There was a problem saving your profile.")

    if st.button("Cancel"):
        st.session_state.edit_profile = False
        st.switch_page("pages/1_Home.py")

else:
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    phone = st.text_input("Phone (optional)")

    if st.button("Submit"):
        if not email or not password or not first_name or not last_name:
            st.error("Email, password, first name, and last name are required.")
        else:
            try:
                auth_response = supabase.auth.sign_up({
                    "email": email,
                    "password": password
                })

                if auth_response.user is None:
                    st.error("Unable to create account.")
                else:
                    user_id = auth_response.user.id

                    profile_response = supabase.table("profiles").insert({
                        "id": user_id,
                        "email": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "phone": phone if phone else None
                    }).execute()

                    if profile_response.data:
                        st.success("Account created. Please log in.")
                        st.switch_page("app.py")
                    else:
                        st.error("Account was created, but profile was not saved.")

            except Exception as e:
                error_text = str(e).lower()

                if "already registered" in error_text:
                    st.error("An account with that email already exists.")
                else:
                    st.error("There was a problem creating your account.")