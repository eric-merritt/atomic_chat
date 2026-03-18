"""Seed the admin user. Run via: python main.py --seed-admin"""

import os
import getpass

import bcrypt

from auth.models import User
from auth.db import get_db


def seed_admin():
    db = get_db()

    # Check if any admin exists
    existing = db.query(User).filter_by(role="admin").first()
    if existing:
        print(f"Admin user already exists: {existing.username} ({existing.email})")
        resp = input("Create another admin? [y/N] ").strip().lower()
        if resp != "y":
            return

    username = input("Admin username: ").strip()
    if not username or len(username) < 3:
        print("Username must be at least 3 characters.")
        return

    if db.query(User).filter_by(username=username).first():
        print(f"Username '{username}' already taken.")
        return

    email = input("Admin email (optional): ").strip() or None
    if email and db.query(User).filter_by(email=email).first():
        print(f"Email '{email}' already registered.")
        return

    password = getpass.getpass("Admin password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        return

    user = User(
        username=username,
        email=email,
        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode(),
        auth_method="local",
        role="admin",
    )
    db.add(user)
    db.commit()

    print(f"Admin user '{username}' created successfully.")


def promote_admin(username: str):
    db = get_db()
    user = db.query(User).filter_by(username=username).first()
    if not user:
        print(f"User '{username}' not found.")
        return
    if user.role == "admin":
        print(f"'{username}' is already an admin.")
        return
    user.role = "admin"
    db.commit()
    print(f"Promoted '{username}' to admin.")
