{
    "name": "Web Chatter Toggle",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "author": "Sanare",
    "license": "LGPL-3",
    "summary": "Collapse or expand the chatter on any form view. The choice is "
    "remembered per model, per browser.",
    "description": """
Adds a small handle to the chatter top bar on every form view. Click it to
collapse the chatter down to a thin strip (only the handle stays visible),
click again to bring it back. The state is stored in the browser's
localStorage keyed by model name, so each model keeps its own preference and
it survives reloads.

No server model, no configuration - just a JS/SCSS patch of the mail Chatter
component.
""",
    "depends": ["mail"],
    "assets": {
        "web.assets_backend": [
            "web_chatter_toggle/static/src/chatter_toggle.scss",
            "web_chatter_toggle/static/src/chatter_toggle.js",
            "web_chatter_toggle/static/src/chatter_toggle.xml",
        ],
    },
    "installable": True,
    "application": False,
}
