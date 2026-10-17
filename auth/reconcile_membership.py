"""Operator-only Stripe membership reconciliation; never exposes a public route."""

import argparse
import json
import os
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="Inspect or reconcile a single Stripe membership order")
    parser.add_argument("--list", action="store_true", help="List unresolved order IDs without personal data")
    parser.add_argument("--order-id", help="The exact AUTOLINK order UUID")
    parser.add_argument("--apply", action="store_true", help="Query Stripe and persist a verified status")
    parser.add_argument("--confirm-order", help="Repeat the order UUID before applying")
    parser.add_argument("--recover-unknown", action="store_true",
                        help="For an unexpired UNKNOWN order, repeat the same idempotent Checkout request")
    parser.add_argument("--environment", choices=("sandbox", "live"),
                        help="Expected Stripe mode; required with --apply")
    args = parser.parse_args()
    if args.list == bool(args.order_id):
        parser.error("choose exactly one of --list or --order-id")
    if args.recover_unknown and not args.apply:
        parser.error("--recover-unknown requires --apply")
    db_path = os.environ.get("AUTH_DB_PATH", "/data/autolink-auth.sqlite3")
    if args.list:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT id,status,created_at,expires_at FROM membership_orders "
                              "WHERE provider='stripe' AND status IN ('CREATING','UNKNOWN','PENDING','REVIEW') "
                              "ORDER BY created_at LIMIT 100").fetchall()
        print(json.dumps([dict(row) for row in rows], separators=(",", ":")))
        return
    if not args.apply:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT id,status,plan,purchase_type,amount_minor,currency,provider_ref "
                             "FROM membership_orders WHERE id=? AND provider='stripe'", (args.order_id,)).fetchone()
        print(json.dumps(dict(row) if row else {"notFound": True}, separators=(",", ":")))
        return
    if args.confirm_order != args.order_id or args.environment != os.environ.get("PAYMENTS_ENV"):
        parser.error("--confirm-order and --environment must match the order and configured Stripe mode")
    from app import AuthService
    from buyer_service import BuyerService
    from membership_payments import MembershipPaymentService

    auth = AuthService(db_path, os.environ.get("GOOGLE_CLIENT_ID", ""), verifier=lambda *_: {})
    BuyerService(auth)
    result = MembershipPaymentService(auth).reconcile_order(args.order_id, args.recover_unknown)
    print(json.dumps({"orderId": args.order_id, **result}, separators=(",", ":")))


if __name__ == "__main__":
    main()
