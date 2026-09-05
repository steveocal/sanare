"""Bootstrap the EOS financial structure in Odoo (idempotent):

- ``cm²`` uom (created if missing)
- 4 wound-care products (THB, price per cm²)
- ``account.budget.post`` for all 12 P&L categories (tagged ``eos_category``,
  each with its mapped ``account_ids`` — the model requires ≥1 account)
- ``eos.account.map`` rows for the specific expense categories so actuals bucket
  correctly (payroll / regulatory / legal / S&M / travel / office)
- 12 monthly ``eos.financial.period`` records (Aug-26 .. Jul-27)

Run:  python3 scripts/eos_financials_setup.py
"""
from sanare_odoo import call
from budget_model import CATEGORIES, CATEGORY_LABELS, build, month_windows

COMPANY_ID = 1

# Account codes per EOS category (Thai chart of accounts). Used to satisfy the
# account.budget.post "must have ≥1 account" constraint AND to tag the posts.
CATEGORY_ACCOUNTS = {
    "revenue":             ["411100", "411200"],
    "cogs":                ["511100", "511200", "511300", "511400", "511500", "511600", "511700"],
    "payroll":             ["611100", "611300", "611400", "611500"],
    "regulatory":          ["611600", "615300", "615400"],
    "legal_prof":          ["615100", "615200"],
    "sales_marketing":     ["611200", "617100", "617200"],
    "travel":              ["619101", "619102", "619103", "619104", "619200"],
    "office_it_ga":        ["613100", "614100", "615500", "618100", "618200",
                            "618300", "618400", "618500", "618700", "622100"],
    "inventory_purchases": ["113100", "113200", "113300"],
    "other_capex":         ["612100", "612200", "612300", "612400", "612500", "612600",
                            "612700", "612800", "612900", "612950", "612960"],
    "other_opex":          ["613200", "613300", "614200", "614300", "615801", "615802",
                            "615803", "615804", "618600", "619300", "619900", "621100"],
    "other_cash":          ["621200", "622200"],
}

# Categories that need explicit account -> category map rows (the rest fall back
# to the built-in account-type defaults in eos.account.map).
SPECIFIC_MAP = {
    "payroll":         ["611100", "611300", "611400", "611500"],
    "regulatory":      ["611600", "615300", "615400"],
    "legal_prof":      ["615100", "615200"],
    "sales_marketing": ["611200", "617100", "617200"],
    "travel":          ["619101", "619102", "619103", "619104", "619200"],
    "office_it_ga":    ["613100", "614100", "615500", "618100", "618200",
                        "618300", "618400", "618500", "618700", "622100"],
}


def account_id_by_code(code):
    ids = call("account.account", "search", [[("code", "=", code)]])
    return ids[0] if ids else None


def ensure_uom():
    found = call("uom.uom", "search_read", [[("name", "=", "cm²")]], {"fields": ["id"]})
    if found:
        return found[0]["id"], False
    uid = call("uom.uom", "create", [{"name": "cm²", "relative_factor": 1.0, "rounding": 0.01}])
    return uid, True


def ensure_products(uom_id):
    d = build()
    created = 0
    for p in d["products"]:
        found = call("product.template", "search_read",
                     [[("name", "=", p["name"])]], {"fields": ["id"]})
        if found:
            continue
        call("product.template", "create", [{
            "name": p["name"],
            "type": "consu",
            "list_price": p["thb_price"],
            "standard_price": p["thb_cost"],
            "uom_id": uom_id,
            "sale_ok": True,
            "purchase_ok": True,
        }])
        created += 1
    return created


def ensure_budget_posts():
    created, patched = 0, 0
    for cat in CATEGORIES:
        acct_ids = [i for i in (account_id_by_code(c) for c in CATEGORY_ACCOUNTS.get(cat, [])) if i]
        if not acct_ids:
            any_acc = call("account.account", "search", [[], {"limit": 1}])
            acct_ids = [any_acc[0]] if any_acc else []
        found = call("account.budget.post", "search_read",
                     [[("eos_category", "=", cat), ("company_id", "=", COMPANY_ID)]],
                     {"fields": ["id", "account_ids"]})
        if found:
            if not found[0]["account_ids"] and acct_ids:
                call("account.budget.post", "write",
                     [[found[0]["id"]], {"account_ids": [(6, 0, acct_ids)]}])
                patched += 1
            continue
        call("account.budget.post", "create", [{
            "name": "EOS Budget: %s" % CATEGORY_LABELS[cat],
            "company_id": COMPANY_ID,
            "eos_category": cat,
            "account_ids": [(6, 0, acct_ids)],
        }])
        created += 1
    return created, patched


def ensure_account_map():
    created = 0
    for cat, codes in SPECIFIC_MAP.items():
        for code in codes:
            aid = account_id_by_code(code)
            if not aid:
                continue
            found = call("eos.account.map", "search_read",
                         [[("account_id", "=", aid), ("category", "=", cat)]],
                         {"fields": ["id"]})
            if found:
                continue
            call("eos.account.map", "create",
                 [{"account_id": aid, "category": cat, "company_id": COMPANY_ID}])
            created += 1
    return created


def ensure_periods():
    created = 0
    for start, end in month_windows():
        found = call("eos.financial.period", "search_read",
                     [[("date_from", "=", start.isoformat()),
                       ("date_to", "=", end.isoformat()),
                       ("company_id", "=", COMPANY_ID)]],
                     {"fields": ["id"]})
        if found:
            continue
        call("eos.financial.period", "create", [{
            "company_id": COMPANY_ID,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "state": "draft",
        }])
        created += 1
    return created


def main():
    uom_id, uom_new = ensure_uom()
    print(f"uom cm²: id={uom_id} {'(created)' if uom_new else '(exists)'}")
    print(f"products created: {ensure_products(uom_id)}")
    created, patched = ensure_budget_posts()
    print(f"budget posts created: {created}, account_ids patched: {patched}")
    print(f"account map rows created: {ensure_account_map()}")
    print(f"financial periods created: {ensure_periods()}")


if __name__ == "__main__":
    main()
