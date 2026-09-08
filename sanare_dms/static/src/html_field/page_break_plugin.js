/** @odoo-module **/

import { Plugin } from "@html_editor/plugin";
import { _t } from "@web/core/l10n/translation";
import { withSequence } from "@html_editor/utils/resource";
import { fillEmpty } from "@html_editor/utils/dom";

// page-break-before is inert on-screen (only wkhtmltopdf/print media honor
// it) - the dashed line + label are purely an editing-time affordance so the
// break is visible and selectable, not part of what actually forces the
// break. data-oe-protected + contenteditable=false keep it a single opaque
// block (selectable/deletable as a whole, not editable inside) - same
// pattern as the embedded-document marker.
const PAGE_BREAK_STYLE = "page-break-before: always; border-top: 2px dashed #999; " +
  "margin: 16px 0; padding-top: 4px; font-size: 11px; color: #999; " +
  "text-transform: uppercase; letter-spacing: .05em; user-select: none;";

export class PageBreakPlugin extends Plugin {
  static id = "sanarePageBreak"
  static dependencies = ["dom", "selection", "history", "baseContainer"]

  resources = {
    user_commands: [
      {
        id: "insertSanarePageBreak",
        title: _t("Page Break"),
        description: _t("Force a new page here when printed"),
        icon: "fa-scissors",
        run: this.insertPageBreak.bind(this),
      },
    ],
    powerbox_items: [
      withSequence(20, {
        categoryId: "structure",
        commandId: "insertSanarePageBreak",
        keywords: [_t("page break"), _t("pagebreak"), _t("print"), _t("new page")],
      }),
    ],
  }

  insertPageBreak() {
    const el = this.document.createElement("div")
    el.setAttribute("class", "sanare_page_break")
    el.setAttribute("data-oe-protected", "true")
    el.setAttribute("contenteditable", "false")
    el.setAttribute("style", PAGE_BREAK_STYLE)
    el.textContent = _t("Page Break")

    this.dependencies.dom.insert(el)

    const baseContainer = this.dependencies.baseContainer.createBaseContainer()
    fillEmpty(baseContainer)
    el.after(baseContainer)
    this.dependencies.selection.setCursorStart(baseContainer)

    this.dependencies.history.addStep()
  }
}
