/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";

const STORAGE_PREFIX = "web_chatter_toggle:";

function readHidden(model) {
    if (!model) {
        return false;
    }
    try {
        return browser.localStorage.getItem(STORAGE_PREFIX + model) === "1";
    } catch {
        return false;
    }
}

function writeHidden(model, hidden) {
    if (!model) {
        return;
    }
    try {
        if (hidden) {
            browser.localStorage.setItem(STORAGE_PREFIX + model, "1");
        } else {
            browser.localStorage.removeItem(STORAGE_PREFIX + model);
        }
    } catch {
        // storage unavailable (private mode, quota) - toggle still works for
        // the current session, it just won't be remembered.
    }
}

// The Chatter component has moved around between Odoo versions
// (@mail/core/web/chatter, @mail/chatter/web/chatter, ...). Resolve it from the
// module loader at service start instead of a hard import that would break the
// whole asset bundle on the wrong path.
function resolveChatter() {
    const known = [
        "@mail/chatter/web/chatter",
        "@mail/core/web/chatter",
        "@mail/core_web/chatter",
    ];
    const modules = odoo.loader.modules;
    for (const path of known) {
        const mod = modules.get(path);
        if (mod && mod.Chatter) {
            return mod.Chatter;
        }
    }
    for (const [, mod] of modules) {
        if (mod && mod.Chatter && mod.Chatter.template === "mail.Chatter") {
            return mod.Chatter;
        }
    }
    return null;
}

function patchChatter(Chatter) {
    patch(Chatter.prototype, {
        setup() {
            super.setup(...arguments);
            this.chatterToggle = useState({
                hidden: readHidden(this.props.threadModel),
            });
        },

        get chatterToggleTitle() {
            return this.chatterToggle.hidden ? _t("Show chatter") : _t("Hide chatter");
        },

        onClickToggleChatter() {
            this.chatterToggle.hidden = !this.chatterToggle.hidden;
            writeHidden(this.props.threadModel, this.chatterToggle.hidden);
        },
    });
}

registry.category("services").add("web_chatter_toggle", {
    start() {
        const Chatter = resolveChatter();
        if (Chatter) {
            patchChatter(Chatter);
        } else {
            console.warn("web_chatter_toggle: Chatter component not found; toggle disabled");
        }
        return {};
    },
});
