#!/usr/bin/env python3
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("/home/rohit_chowdary/Rohit-AI-WorkSpace/marketplace/marketplace.db")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON;")

        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS creators (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              primary_name TEXT NOT NULL,
              linktree_domain TEXT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS social_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              creator_id INTEGER NULL,
              platform TEXT NOT NULL CHECK(platform IN ('instagram','youtube','facebook')),
              profile_url TEXT NOT NULL UNIQUE,
              handle TEXT NULL,
              display_name TEXT NULL,
              bio TEXT NULL,
              external_website TEXT NULL,
              linktree_domain TEXT NULL,
              profile_image_hash TEXT NULL,
              followers INTEGER NULL,
              following INTEGER NULL,
              posts INTEGER NULL,
              total_views INTEGER NULL,
              avg_views_last_10 REAL NULL,
              avg_likes_last_10 REAL NULL,
              avg_comments_last_10 REAL NULL,
              posting_frequency_per_week REAL NULL,
              data_confidence TEXT NOT NULL DEFAULT 'low' CHECK(data_confidence IN ('low','medium','high')),
              identity_status TEXT NOT NULL DEFAULT 'standalone' CHECK(identity_status IN ('standalone','linked','needs_review')),
              source TEXT NOT NULL DEFAULT 'discovered' CHECK(source IN ('discovered','self_registered')),
              created_at TEXT NOT NULL,
              last_fetched_at TEXT NULL,
              FOREIGN KEY (creator_id) REFERENCES creators(id)
            );

            CREATE TABLE IF NOT EXISTS profile_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              social_profile_id INTEGER NOT NULL,
              followers INTEGER NULL,
              total_views INTEGER NULL,
              avg_views_last_10 REAL NULL,
              avg_likes_last_10 REAL NULL,
              avg_comments_last_10 REAL NULL,
              posting_frequency_per_week REAL NULL,
              timestamp TEXT NOT NULL,
              FOREIGN KEY (social_profile_id) REFERENCES social_profiles(id)
            );

            CREATE TABLE IF NOT EXISTS identity_suggestions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              social_profile_id INTEGER NOT NULL,
              suggested_creator_id INTEGER NOT NULL,
              reason TEXT NOT NULL,
              confidence REAL NOT NULL,
              status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','accepted','rejected')),
              created_at TEXT NOT NULL,
              FOREIGN KEY (social_profile_id) REFERENCES social_profiles(id),
              FOREIGN KEY (suggested_creator_id) REFERENCES creators(id)
            );

            CREATE INDEX IF NOT EXISTS idx_social_profiles_platform_handle
              ON social_profiles(platform, handle);

            CREATE INDEX IF NOT EXISTS idx_social_profiles_linktree_domain
              ON social_profiles(linktree_domain);

            CREATE INDEX IF NOT EXISTS idx_profile_snapshots_profile_timestamp
              ON profile_snapshots(social_profile_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_identity_suggestions_status
              ON identity_suggestions(status);
            """
        )

        con.commit()
        print(f"DB ready at {DB_PATH}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
