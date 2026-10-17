"""Operator-only Stripe supplier listing order inspection and reconciliation."""

import argparse
import json
import os
import sqlite3


def main():
    parser = argparse.ArgumentParser(description="Inspect or reconcile one Stripe supplier listing order")
    parser.add_argument("--list", action="store_true", help="List unresolved order IDs")
    parser.add_argument("--order-id", help="Exact AUTOLINK supplier listing order ID")
    parser.add_argument("--apply", action="store_true", help="Query Stripe and persist verified status")
    parser.add_argument("--confirm-order", help="Repeat the order ID before applying")
    parser.add_argument("--recover-unknown", action="store_true",
                        help="Retry the same idempotent Checkout request before expiry")
    parser.add_argument("--environment", choices=("sandbox", "live"),
                        help="Required Stripe environment for --apply")
    args = parser.parse_args()
    if args.list == bool(args.order_id):
        parser.error("choose exactly one of --list or --order-id")
    if args.recover_unknown and not args.apply:
        parser.error("--recover-unknown requires --apply")
    db_path = os.environ.get("AUTH_DB_PATH", "/data/autolink-auth.sqlite3")
    if not args.apply:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            if args.list:
                rows = db.execute(
                    "SELECT id,status,created_at,expires_at FROM supplier_listing_orders "
                    "WHERE provider='stripe' AND status IN ('CREATING','UNKNOWN','PENDING') "
                    "ORDER BY created_at LIMIT 100"
                ).fetchall()
                print(json.dumps([dict(row) for row in rows], separators=(",", ":")))
            else:
                row = db.execute(
                    "SELECT id,status,quarter_number,amount_minor,currency,provider_ref,"
                    "refund_status,dispute_status FROM supplier_listing_orders "
                    "WHERE id=? AND provider='stripe'", (args.order_id,)
                ).fetchone()
                print(json.dumps(dict(row) if row else {"notFound": True}, separators=(",", ":")))
        return
    if args.confirm_order != args.order_id or args.environment != os.environ.get("PAYMENTS_ENV"):
        parser.error("--confirm-order and --environment must match the order and configured Stripe mode")
    from app import AuthService
    from trade_service import TradeService
    from supplier_listing_payments import SupplierListingPayments

    auth = AuthService(db_path, os.environ.get("GOOGLE_CLIENT_ID", ""), verifier=lambda *_: {})
    result = SupplierListingPayments(TradeService(auth)).reconcile_order(
        args.order_id, args.recover_unknown)
    print(json.dumps({"orderId": args.order_id, **result}, separators=(",", ":")))


if __name__ == "__main__":
    main()
