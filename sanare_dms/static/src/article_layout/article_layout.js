/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";

// Companion to the sanare.document form's split layout (dms_document_views.xml,
// .o_dms_article_layout/.o_dms_article_side/.o_dms_article_resize). Deliberately
// plain DOM + event delegation, same shape as web_chatter_toggle's localStorage
// approach, rather than an OWL widget bound into the form: the arch renders
// identically whether this view is opened standalone or mounted inline inside
// DmsBrowser's detail pane (see DmsDocForm), and a global delegated listener
// works the same in both without needing to know which one it's in.

const WIDTH_KEY = "sanare_dms:article_side_width";
const COLLAPSED_KEY = "sanare_dms:article_side_collapsed";
const MIN_WIDTH = 260;
const MAX_WIDTH = 720;

function applyStoredState(layout) {
    const side = layout.querySelector(":scope > .o_dms_article_side");
    if (!side) {
        return;
    }
    try {
        const width = browser.localStorage.getItem(WIDTH_KEY);
        if (width) {
            side.style.width = width + "px";
        }
        const collapsed = browser.localStorage.getItem(COLLAPSED_KEY) === "1";
        layout.classList.toggle("o_dms_side_collapsed", collapsed);
    } catch {
        // localStorage unavailable (private mode, quota) - layout just keeps
        // its default width/open state for this session.
    }
}

registry.category("services").add("sanare_dms_article_layout", {
    start() {
        // Form mounting is async and this class can appear anywhere in the
        // DOM (standalone action or embedded in DmsBrowser) - a MutationObserver
        // is the only reliable way to catch it without hooking into either
        // rendering path directly.
        const seen = new WeakSet();
        const scan = () => {
            document.querySelectorAll(".o_dms_article_layout").forEach((layout) => {
                if (!seen.has(layout)) {
                    seen.add(layout);
                    applyStoredState(layout);
                }
            });
        };
        new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
        scan();

        document.body.addEventListener("click", (ev) => {
            const toggle = ev.target.closest(
                ".o_dms_article_side_toggle, .o_dms_article_edge_toggle"
            );
            if (!toggle) {
                return;
            }
            const layout = toggle.closest(".o_dms_article_layout");
            if (!layout) {
                return;
            }
            const collapsed = !layout.classList.contains("o_dms_side_collapsed");
            layout.classList.toggle("o_dms_side_collapsed", collapsed);
            try {
                if (collapsed) {
                    browser.localStorage.setItem(COLLAPSED_KEY, "1");
                } else {
                    browser.localStorage.removeItem(COLLAPSED_KEY);
                }
            } catch {
                // best-effort persistence only
            }
        });

        let drag = null;
        document.body.addEventListener("mousedown", (ev) => {
            const handle = ev.target.closest(".o_dms_article_resize");
            if (!handle) {
                return;
            }
            const layout = handle.closest(".o_dms_article_layout");
            const side = layout && layout.querySelector(":scope > .o_dms_article_side");
            if (!side) {
                return;
            }
            drag = { side, startX: ev.clientX, startWidth: side.getBoundingClientRect().width };
            ev.preventDefault();
        });
        window.addEventListener("mousemove", (ev) => {
            if (!drag) {
                return;
            }
            // The panel sits on the right, so dragging left (negative delta)
            // should widen it.
            const delta = drag.startX - ev.clientX;
            const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, drag.startWidth + delta));
            drag.side.style.width = width + "px";
        });
        window.addEventListener("mouseup", () => {
            if (!drag) {
                return;
            }
            try {
                browser.localStorage.setItem(
                    WIDTH_KEY, String(Math.round(drag.side.getBoundingClientRect().width))
                );
            } catch {
                // best-effort persistence only
            }
            drag = null;
        });

        return {};
    },
});
