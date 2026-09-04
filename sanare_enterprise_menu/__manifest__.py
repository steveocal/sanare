{
    "name": "Sanare Enterprise Menu",
    "version": "19.0.1.0.0",
    "category": "Theme/Backend",
    "summary": "Enterprise-style app menu (icon grid + search) for the Odoo Community edition",
    "author": "Sanare",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "sanare_enterprise_menu/static/src/js/apps_menu.js",
            "sanare_enterprise_menu/static/src/xml/apps_menu.xml",
            "sanare_enterprise_menu/static/src/scss/apps_menu.scss"
        ]
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3"
}
