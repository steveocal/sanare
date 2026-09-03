"""Post-install seeding: one ``account.budget.post`` per EOS P&L category.

The plan side of budget-vs-actual lives in ``base_account_budget``. A
budgetary position tagged with ``eos_category`` is the bucket the monthly
``eos.financial.period`` reads its budget from. We create one per category
that has at least one account resolved by ``eos.account.map`` and does not
already have a tagged position.
"""
from .models.account_map import PL_CATEGORIES


def post_init_seed_budget_posts(env):
    Map = env['eos.account.map']
    Post = env['account.budget.post']
    Account = env['account.account']
    labels = dict(PL_CATEGORIES)

    for company in env['res.company'].search([]):
        map_env = Map.with_company(company)
        buckets = {}
        for account in Account.with_company(company).search([]):
            category = map_env._category_for_account(account)
            if category in labels:
                buckets.setdefault(category, Account)
                buckets[category] |= account

        for category, accounts in buckets.items():
            if not accounts:
                continue
            existing = Post.search([
                ('eos_category', '=', category),
                ('company_id', '=', company.id),
            ], limit=1)
            if existing:
                continue
            Post.create({
                'name': 'EOS Budget: %s' % labels[category],
                'company_id': company.id,
                'eos_category': category,
                'account_ids': [(6, 0, accounts.ids)],
            })
