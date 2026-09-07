from odoo.addons.sanare_dms import _link_dms_user_to_internal


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    _link_dms_user_to_internal(env)
