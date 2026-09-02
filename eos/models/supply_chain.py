from odoo import api, fields, models


class EosSku(models.Model):
    _name = 'eos.sku'
    _description = 'EOS Supply Chain / Inventory (SKU)'
    _order = 'name'

    name = fields.Char(string='SKU / Product', required=True)
    market_id = fields.Many2one('eos.market', string='Market')
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse',
        help='Restrict the on-hand read to one warehouse; leave empty for company-wide on-hand.')
    manufacturer = fields.Char(string='Manufacturer')
    cm2_per_unit = fields.Float(
        string='cm2 per Unit', default=1.0,
        help='Conversion factor: graft cm2 represented by one stockable unit of the product.')
    # Not stored: qty_available is itself a non-stored computed field, so a stored
    # mirror here would never be refreshed by stock moves. Computed live on read.
    inventory_cm2 = fields.Float(
        string='Inventory cm2', compute='_compute_inventory',
        help='On-hand quantity from Odoo Inventory, converted to cm2.')
    inventory_value = fields.Monetary(
        string='Inventory Value', compute='_compute_inventory',
        currency_field='currency_id')
    open_po_cm2 = fields.Float(string='Open PO cm2')
    open_po_amount = fields.Monetary(string='Open PO $', currency_field='currency_id')
    avg_landed_cost_cm2 = fields.Float(string='Avg Landed Cost/cm2')
    weeks_supply = fields.Float(string='Weeks Supply')
    earliest_expiry = fields.Date(string='Earliest Expiry')
    stockout_risk = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], string='Stockout Risk', default='green')
    last_receipt = fields.Date(string='Last Receipt')
    owner = fields.Char(string='Owner')
    currency_id = fields.Many2one(
        'res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    notes = fields.Text(string='Notes')

    @api.depends('product_id', 'warehouse_id', 'cm2_per_unit',
                 'product_id.qty_available', 'product_id.standard_price')
    def _compute_inventory(self):
        for sku in self:
            product = sku.product_id
            if not product:
                sku.inventory_cm2 = 0.0
                sku.inventory_value = 0.0
                continue
            if sku.warehouse_id:
                product = product.with_context(warehouse_id=sku.warehouse_id.id)
            factor = sku.cm2_per_unit or 1.0
            qty = product.qty_available
            sku.inventory_cm2 = qty * factor
            sku.inventory_value = qty * product.standard_price
