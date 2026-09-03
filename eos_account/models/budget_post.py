from odoo import fields, models

from .account_map import PL_CATEGORIES


class AccountBudgetPost(models.Model):
    """A budgetary position (from base_account_budget) can be tagged as the
    EOS budget bucket for one P&L category. eos.financial.period then reads
    its budget figures from the budget.lines under that position."""
    _inherit = 'account.budget.post'

    eos_category = fields.Selection(
        PL_CATEGORIES, string='EOS Report Category',
        help='Marks this budgetary position as the EOS budget bucket for the '
             'given P&L category. The monthly financial period prorates the '
             'budget lines under this position onto its date window.')

    _uniq_eos_category = models.Constraint(
        'unique(company_id, eos_category)',
        'Only one budgetary position per company can represent an EOS category.',
    )
