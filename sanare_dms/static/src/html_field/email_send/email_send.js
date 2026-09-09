/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { _t } from "@web/core/l10n/translation"
import * as embedUtils from "@html_editor/others/embedded_component_utils"
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector"

const RECIPIENT_ROWS = [
  { field: "to", label: _t("To") },
  { field: "cc", label: _t("Cc") },
  { field: "bcc", label: _t("Bcc") },
]

const DEFAULT_STATE = { subject: "", to: [], cc: [], bcc: [], lastSend: null }

// The block manages its own data-embedded-props by hand rather than through
// useEmbeddedState (that helper needs a StateChangeManager wired into the
// embedding, and its internals vary between Odoo builds). Reading props is
// the same getEmbeddedProps call embedded_doc_ref relies on; writing is a
// setAttribute on the (protected) host node - the editor serialises the
// live DOM on save, and send() force-saves first, so the stored value is
// current when it matters. Trade-off: editing the block alone doesn't flip
// the form's "unsaved" dot - use Save (or Send).
function readProps(host) {
  try {
    return { ...DEFAULT_STATE, ...(embedUtils.getEmbeddedProps?.(host) || {}) }
  } catch {
    return { ...DEFAULT_STATE }
  }
}

export class EmbeddedEmailSendComponent extends Component {
  static template = "sanare_dms.EmbeddedEmailSend"
  static components = { MultiRecordSelector }
  static props = {
    host: { type: Object },
  }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.action = useService("action")

    // {subject, to, cc, bcc, lastSend}; to/cc/bcc are arrays of partner ids.
    this.state = useState(readProps(this.props.host))
    this.ui = useState({ sending: false })
  }

  get rows() {
    return RECIPIENT_ROWS
  }

  ids(field) {
    return this.state[field] || []
  }

  persist() {
    this.props.host.setAttribute(
      "data-embedded-props",
      JSON.stringify({
        subject: this.state.subject,
        to: this.state.to,
        cc: this.state.cc,
        bcc: this.state.bcc,
        lastSend: this.state.lastSend,
      })
    )
    try {
      this.props.host.dispatchEvent(new InputEvent("input", { bubbles: true }))
    } catch {
      // InputEvent unsupported - the save path still re-reads the DOM.
    }
  }

  setRecipients(field, ids) {
    this.state[field] = ids || []
    this.persist()
  }

  onSubjectInput(ev) {
    this.state.subject = ev.target.value
    this.persist()
  }

  // ---- last-send result -----------------------------------------
  get lastSendLabel() {
    const ls = this.state.lastSend
    if (!ls || !ls.state) {
      return _t("Never sent")
    }
    if (ls.state === "failed") {
      return ls.date ? _t("Failed — %s", ls.date) : _t("Failed")
    }
    return _t("Sent %s", ls.date || "")
  }

  get lastSendClass() {
    const ls = this.state.lastSend
    if (!ls || !ls.state) {
      return "text-muted"
    }
    return ls.state === "failed" ? "text-danger" : "text-success"
  }

  // ---- send -----------------------------------------------------
  get documentId() {
    if (this.env.model?.root?.resId) {
      return this.env.model.root.resId
    }
    const wrap = this.props.host.closest('[data-oe-model="sanare.document"]')
    return wrap ? parseInt(wrap.dataset.oeId, 10) || false : false
  }

  bodyHtml() {
    const editable =
      this.props.host.closest(".odoo-editor-editable") ||
      this.props.host.closest("[contenteditable='true']")
    if (!editable) {
      return ""
    }
    const clone = editable.cloneNode(true)
    clone
      .querySelectorAll('[data-embedded="sanareEmailSend"]')
      .forEach((n) => n.remove())
    return clone.innerHTML
  }

  async send() {
    if (!this.ids("to").length) {
      this.notification.add(_t("Add at least one “To” recipient."), { type: "warning" })
      return
    }
    if (!(this.state.subject || "").trim()) {
      this.notification.add(_t("Add a subject."), { type: "warning" })
      return
    }

    this.ui.sending = true
    try {
      this.persist()
      if (this.env.model?.root) {
        await this.env.model.root.save()
      }
      const documentId = this.documentId
      if (!documentId) {
        this.notification.add(_t("Save the document first."), { type: "warning" })
        return
      }

      const res = await this.orm.call("sanare.document", "send_email_block", [
        documentId,
        {
          subject: this.state.subject,
          to_ids: this.ids("to"),
          cc_ids: this.ids("cc"),
          bcc_ids: this.ids("bcc"),
          body_html: this.bodyHtml(),
        },
      ])

      if (res.error === "no_email") {
        this.notification.add(
          _t("These contacts have no email address: %s", res.partners_without_email.join(", ")),
          {
            type: "danger",
            buttons:
              res.partner_ids && res.partner_ids.length
                ? [
                    {
                      name: _t("Open contact"),
                      onClick: () =>
                        this.action.doAction({
                          type: "ir.actions.act_window",
                          res_model: "res.partner",
                          res_id: res.partner_ids[0],
                          views: [[false, "form"]],
                          target: "new",
                        }),
                    },
                  ]
                : [],
          }
        )
        return
      }

      this.state.lastSend = { state: res.state, date: res.date, error: res.error || "" }
      this.persist()
      this.notification.add(
        res.state === "failed" ? _t("Send failed: %s", res.error || "") : _t("Email sent."),
        { type: res.state === "failed" ? "danger" : "success" }
      )
    } catch (e) {
      this.notification.add(_t("Could not send the email."), { type: "danger" })
      throw e
    } finally {
      this.ui.sending = false
    }
  }
}

export const emailSendEmbedding = {
  name: "sanareEmailSend",
  Component: EmbeddedEmailSendComponent,
  getProps: (host) => ({ host }),
}
