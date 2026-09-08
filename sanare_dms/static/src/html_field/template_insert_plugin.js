/** @odoo-module **/

import { Plugin } from "@html_editor/plugin"
import { _t } from "@web/core/l10n/translation"
import { parseHTML } from "@html_editor/utils/html"
import { fillEmpty } from "@html_editor/utils/dom"
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog"

// Deliberately NOT built like EmbeddedDocRefPlugin (embedded_doc_ref_plugin.js)
// even though the picker step looks the same: that one stores a live
// reference (a marker the editor re-fetches on every mount); this one is a
// one-time copy - the template's resolved content is inserted as plain,
// independently-editable HTML, no ongoing link back to the template
// afterwards. That's the point of a template versus an embed.
export class TemplateInsertPlugin extends Plugin {
  static id = "sanareTemplateInsert"
  static dependencies = ["dom", "selection", "history", "baseContainer", "dialog"]

  resources = {
    user_commands: [
      {
        id: "insertSanareTemplate",
        title: _t("Insert Template"),
        description: _t("Copy in a template's content - a one-time paste, not a live link"),
        icon: "fa-magic",
        run: this.openPicker.bind(this),
      },
    ],
    powerbox_items: [
      {
        categoryId: "structure",
        commandId: "insertSanareTemplate",
        keywords: [_t("template"), _t("insert"), _t("boilerplate")],
      },
    ],
  }

  openPicker() {
    const recordInfo = this.config.getRecordInfo?.()
    const domain = [
      ["is_template", "=", true],
      ["content_type", "in", ["html", "knowledge_html"]],
    ]
    if (recordInfo?.resId) {
      domain.push(["id", "!=", recordInfo.resId])
    }

    this.dependencies.dialog.addDialog(SelectCreateDialog, {
      resModel: "sanare.document",
      title: _t("Insert a Template"),
      domain,
      multiSelect: false,
      noCreate: true,
      onSelected: (resIds) => {
        if (resIds?.length) {
          this.insertTemplate(resIds[0]);
        }
      },
    })
  }

  async insertTemplate(documentId) {
    const data = await this.services.orm.call("sanare.document", "get_template_content", [documentId])
    if (data.error) {
      this.services.notification.add(
        _t("This template is no longer available."), { type: "danger" }
      )
      return
    }

    const fragment = parseHTML(this.document, data.content_html || "")
    if (!fragment.hasChildNodes()) {
      return
    }
    // parseHTML's fragment empties out (children get moved) the moment
    // dom.insert() attaches them, so grab the last child now for the
    // "somewhere to keep typing" step below.
    const lastEl = fragment.lastElementChild
    this.dependencies.dom.insert(fragment)

    if (lastEl) {
      const baseContainer = this.dependencies.baseContainer.createBaseContainer()
      fillEmpty(baseContainer)
      lastEl.after(baseContainer)
      this.dependencies.selection.setCursorStart(baseContainer)
    }

    this.dependencies.history.addStep()
  }
}
