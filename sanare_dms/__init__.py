from . import models
from . import wizard
from . import controllers


def _link_dms_user_to_internal(env):
    """Make every internal user a Document User so the app is visible to all.

    ``base.group_user`` is flagged ``noupdate`` by the ``base`` module, so an
    XML ``<record id="base.group_user">`` in this module is skipped on module
    update. Do it in code instead (install hook + migration).
    """
    from odoo import Command

    internal = env.ref("base.group_user", raise_if_not_found=False)
    dms_user = env.ref("sanare_dms.group_dms_user", raise_if_not_found=False)
    if internal and dms_user and dms_user not in internal.implied_ids:
        internal.write({"implied_ids": [Command.link(dms_user.id)]})


def post_init_hook(env):
    _link_dms_user_to_internal(env)
