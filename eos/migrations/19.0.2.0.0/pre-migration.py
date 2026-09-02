"""eos.physician becomes a delegate of res.partner (_inherits).

Before the new schema drops eos_physician.name / .market_id and enforces a
required partner_id, create a res.partner for every physician row that has no
contact yet and backfill the FK.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return  # fresh install, nothing to migrate

    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'eos_physician'"
    )
    if not cr.fetchone():
        return

    cr.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_name = 'eos_physician' AND column_name = 'partner_id'"""
    )
    if not cr.fetchone():
        cr.execute("ALTER TABLE eos_physician ADD COLUMN partner_id integer")

    cr.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_name = 'eos_physician'
             AND column_name IN ('name', 'market_id')"""
    )
    cols = {r[0] for r in cr.fetchall()}
    name_col = 'name' if 'name' in cols else 'NULL'
    market_col = 'market_id' if 'market_id' in cols else 'NULL'

    cr.execute(
        "SELECT id, %s, %s FROM eos_physician WHERE partner_id IS NULL"
        % (name_col, market_col)
    )
    rows = cr.fetchall()
    if not rows:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    for phys_id, name, market_id in rows:
        partner = env['res.partner'].create({
            'name': name or 'Physician',
            'is_physician': True,
            'market_id': market_id or False,
        })
        cr.execute(
            "UPDATE eos_physician SET partner_id = %s WHERE id = %s",
            (partner.id, phys_id),
        )
