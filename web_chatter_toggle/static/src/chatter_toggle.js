/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
// Odoo 19 path. On Odoo 17/18 this component lives at "@mail/core/web/chatter".
import { Chatter } from "@mail/chatter/web/chatter";

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
        // storage unavailable (private mode, quota) - the toggle still works
        // for the current session, it just won't be remembered.
    }
}

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
