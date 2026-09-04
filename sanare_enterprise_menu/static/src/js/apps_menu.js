/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.appsMenu = useState({ query: "" });
    },

    get filteredApps() {
        const query = this.appsMenu.query.trim().toLowerCase();
        const apps = this.menuService.getApps();
        if (!query) {
            return apps;
        }
        return apps.filter((app) => app.name.toLowerCase().includes(query));
    },
});
