/** @odoo-module **/

import { Plugin } from "@html_editor/plugin"
import { _t } from "@web/core/l10n/translation"
import { renderToString } from "@web/core/utils/render"
import { parseHTML } from "@html_editor/utils/html"
import { fillEmpty } from "@html_editor/utils/dom"
import { emailSendEmbedding } from "./email_send"

// Same shape as EmbeddedDocRefPlugin (embedded_doc_ref_plugin.js): a "/"
// command drops an empty protected marker, an embedded OWL component
// renders it live. The marker's data-embedded-props carries the block's
// entire state (subject + To/Cc/Bcc + last-send result); nothing about
// the email touches the model.
export class EmailSendPlugin extends Plugin {
  static id = "sanareEmailSend"
  static dependencies = ["dom", "selection", "history", "embeddedComponents", "baseContainer"]

  resources = {
    user_commands: [
      {
        id: "insertSanareEmailSend",
        title: _t("Send Email"),
        description: _t("Turn this document into a sendable email"),
        icon: "fa-paper-plane",
        run: this.insertBlock.bind(this),
      },
    ],
    powerbox_items: [
      {
        categoryId: "structure",
        commandId: "insertSanareEmailSend",
        keywords: [_t("email"), _t("send"), _t("mail"), _t("message")],
      },
    ],
    embedded_components: [emailSendEmbedding],
  }

  insertBlock() {
    // One email block per document - a second one would just be a
    // confusing duplicate control bar over the same body.
    if (this.editable.querySelector('[data-embedded="sanareEmailSend"]')) {
      this.services.notification.add(
        _t("This document already has an email block."),
        { type: "warning" }
      )
      return
    }

    const block = parseHTML(
      this.document,
      renderToString("sanare_dms.EmbeddedEmailSendBlueprint", {
        embeddedProps: JSON.stringify({
          subject: "",
          to: [],
          cc: [],
          bcc: [],
          lastSend: null,
        }),
      })
    )
    const hostEl = block.querySelector('[data-embedded="sanareEmailSend"]')
    this.dependencies.dom.insert(block)

    // Somewhere to keep typing right after the block (same fix the
    // Separator command and EmbeddedDocRefPlugin apply).
    const baseContainer = this.dependencies.baseContainer.createBaseContainer()
    fillEmpty(baseContainer)
    hostEl.after(baseContainer)
    this.dependencies.selection.setCursorStart(baseContainer)

    this.dependencies.history.addStep()
  }
}
