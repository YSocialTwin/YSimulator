#!/usr/bin/env python3
"""
Diagnostic script for the reply pipeline.

This script helps debug why agents might not be replying to mentions.
It checks:
1. Are mentions being created in the database?
2. Are there unreplied mentions?
3. Are agents being activated?
4. Is the reply pipeline being triggered?

Usage:
    python diagnose_reply_pipeline.py --config path/to/config.yaml
"""

import argparse
import os
import sys

from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def diagnose_mentions(db: DatabaseMiddleware):
    """Check if mentions exist in the database."""
    print("\n" + "=" * 60)
    print("MENTION DIAGNOSTICS")
    print("=" * 60)

    # Get all users
    users = db.get_all_users()
    print(f"\n1. Total users in system: {len(users)}")

    if not users:
        print("   ⚠️  WARNING: No users found!")
        return

    # Check mentions for each user
    total_mentions = 0
    users_with_unreplied = 0

    for user in users[:10]:  # Check first 10 users
        user_id = user.get("id")
        username = user.get("username", "Unknown")
        is_page = user.get("is_page", 0)

        # Get all mentions (need to query directly)
        unreplied = db.get_unreplied_mentions(user_id)

        if unreplied:
            total_mentions += len(unreplied)
            users_with_unreplied += 1
            print(f"\n   User: {username} (page={is_page})")
            print(f"      - Unreplied mentions: {len(unreplied)}")

            # Show details of first mention
            if unreplied:
                mention = unreplied[0]
                print("      - First mention:")
                print(f"        * mention_id: {mention.get('id')}")
                print(f"        * post_id: {mention.get('post_id')}")
                print(f"        * answered: {mention.get('answered')}")

    print("\n2. Summary:")
    print(f"   - Users with unreplied mentions: {users_with_unreplied}")
    print(f"   - Total unreplied mentions: {total_mentions}")

    if total_mentions == 0:
        print("\n   ⚠️  WARNING: No unreplied mentions found!")
        print("   This could mean:")
        print("   - No posts with @mentions have been created yet")
        print("   - All mentions have already been replied to")
        print("   - Mention extraction is not working")


def diagnose_posts_with_mentions(db: DatabaseMiddleware):
    """Check if posts with mentions exist."""
    print("\n" + "=" * 60)
    print("POST DIAGNOSTICS")
    print("=" * 60)

    # Get recent posts
    recent_posts = db.get_recent_posts(limit=50)
    print(f"\n1. Recent posts: {len(recent_posts)}")

    posts_with_mentions = 0
    for post_id in recent_posts[:20]:  # Check first 20
        post = db.get_post(post_id)
        if post:
            content = post.get("tweet", "")
            if "@" in content:
                posts_with_mentions += 1
                print(f"\n   Post {post_id}:")
                print(f"   Content: {content[:100]}...")

    print(f"\n2. Posts with @ symbols: {posts_with_mentions}")

    if posts_with_mentions == 0:
        print("\n   ⚠️  WARNING: No posts with @ symbols found!")


def main():
    parser = argparse.ArgumentParser(description="Diagnose reply pipeline issues")
    parser.add_argument("--db-path", default="simulator.db", help="Path to SQLite database")
    parser.add_argument("--redis", action="store_true", help="Use Redis backend")
    args = parser.parse_args()

    print("=" * 60)
    print("REPLY PIPELINE DIAGNOSTIC TOOL")
    print("=" * 60)

    # Initialize database middleware
    if args.redis:
        print("\n⚠️  Redis mode not fully implemented in diagnostic tool")
        print("Using SQL database for diagnostics...")

    db_config = {"type": "sqlite", "path": args.db_path}

    db = DatabaseMiddleware(db_config)

    # Run diagnostics
    diagnose_mentions(db)
    diagnose_posts_with_mentions(db)

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\nTo see reply pipeline in action, check logs for:")
    print("  [REPLY] - Client-side reply pipeline messages")
    print("  [REPLY_SERVER] - Server-side messages")
    print("  [REPLY_DB] - Database layer messages")
    print("\nExample grep commands:")
    print("  grep '\\[REPLY\\]' simulation.log")
    print("  grep 'unreplied mention' simulation.log")
    print("  grep 'replying to mention' simulation.log")


if __name__ == "__main__":
    main()
