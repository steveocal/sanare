/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { _t } from "@web/core/l10n/translation"
import * as embedUtils from "@html_editor/others/embedded_component_utils"

const DEFAULT = { subject: "", to: [], cc: [], bcc: [], lastSend: null }
// to / cc / bcc are arrays of { id, name }.

function readProps(host) {
  try {
    return { ...DEFAULT, ...(embedUtils.getEmbeddedProps?.(host) || {}) }
  } catch {
    return { ...DEFAULT }
  }
}

// Deliberately no third-party pickers (AutoComplete / MultiRecordSelector /
// TagsList): their prop schemas are what broke earlier iterations. This is
// a plain input + orm.searchRead dropdown + plain chips - only bedrock ORM
// calls. State persists straight into data-embedded-props (no
// useEmbeddedState, which needs a StateChangeManager wired into the
// embedding). send() force-saves and the editor re-reads the DOM on save,
// so the stored value is current when it matters.
export class EmbeddedEmailSendComponent extends Component {
  static template = "sanare_dms.EmbeddedEmailSend"
  static props = { host: { type: Object } }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.action = useService("action")
    this.state = useState(readProps(this.props.host))
    this.ui = useState({
      sending: false,
      pick: {
        to: { q: "", results: [], open: false },
        cc: { q: "", results: [], open: false },
        bcc: { q: "", results: [], open: false },
      },
    })
    this._seq = 0
  }

  get rows() {
    return [
      { f: "to", l: _t("To") },
      { f: "cc", l: _t("Cc") },
      { f: "bcc", l: _t("Bcc") },
    ]
  }

  list(f) {
    return this.state[f] || []
  }

  pk(f) {
    return this.ui.pick[f]
  }

  persist() {
    try {
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
      const editable = this.props.host.closest(".odoo-editor-editable")
      ;(editable || this.props.host).dispatchEvent(new Event("input", { bubbles: true }))
    } catch {
      // The save path re-reads the DOM regardless.
    }
  }

  // ---- subject --------------------------------------------------
  onSubject(ev) {
    this.state.subject = ev.target.value
    this.persist()
  }

  // ---- recipients ----------------------------------------------
  async onSearch(f, ev) {
    const q = ev.target.value
    this.pk(f).q = q
    const seq = ++this._seq
    if (!q.trim()) {
      this.pk(f).results = []
      this.pk(f).open = false
      return
    }
    const chosen = this.list(f).map((r) => r.id)
    const domain = ["|", ["name", "ilike", q], ["email", "ilike", q]]
    if (chosen.length) {
      domain.push(["id", "not in", chosen])
    }
    let recs = []
    try {
      recs = await this.orm.searchRead("res.partner", domain, ["display_name", "email"], {
        limit: 6,
      })
    } catch {
      this.notification.add(_t("Contact search failed."), { type: "danger" })
      return
    }
    if (seq !== this._seq) {
      return
    }
    this.pk(f).results = recs
    this.pk(f).open = true
  }

  add(f, rec) {
    if (!this.list(f).some((r) => r.id === rec.id)) {
      this.state[f] = [
        ...this.list(f),
        { id: rec.id, name: rec.display_name || rec.name || _t("Contact") },
      ]
    }
    this.pk(f).q = ""
    this.pk(f).results = []
    this.pk(f).open = false
    this.persist()
  }

  async createContact(f) {
    const name = this.pk(f).q.trim()
    if (!name) {
      return
    }
    try {
      const [id, displayName] = await this.orm.call("res.partner", "name_create", [name])
      this.add(f, { id, display_name: displayName })
    } catch {
      this.notification.add(_t("Could not create the contact."), { type: "danger" })
    }
  }

  remove(f, id) {
    this.state[f] = this.list(f).filter((r) => r.id !== id)
    this.persist()
  }

  onBlur(f) {
    // Delay so a mousedown on a result registers before the list closes.
    setTimeout(() => {
      this.pk(f).open = false
    }, 150)
  }

  // ---- last send result --------------------------------------
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

  // ---- send --------------------------------------------------
  get documentId() {
    if (this.env.model?.root?.resId) {
      return this.env.model.root.resId
    }
    const wrap = this.props.host.closest('[data-oe-model="sanare.document"]')
    return wrap ? parseInt(wrap.dataset.oeId, 10) || false : false
  }

  async send() {
    if (!this.list("to").length) {
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
          to_ids: this.list("to").map((r) => r.id),
          cc_ids: this.list("cc").map((r) => r.id),
          bcc_ids: this.list("bcc").map((r) => r.id),
        },
      ])
      if (res.error === "no_email") {
        this.notification.add(
          _t("These contacts have no email address: %s", res.partners_without_email.join(", ")),
          { type: "danger" }
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
