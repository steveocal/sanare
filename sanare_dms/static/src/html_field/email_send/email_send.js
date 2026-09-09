/** @odoo-module **/

import { Component, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { _t } from "@web/core/l10n/translation"
import * as embedUtils from "@html_editor/others/embedded_component_utils"
import { AutoComplete } from "@web/core/autocomplete/autocomplete"
import { TagsList } from "@web/core/tags_list/tags_list"

const RECIPIENT_ROWS = [
  { field: "to", label: _t("To") },
  { field: "cc", label: _t("Cc") },
  { field: "bcc", label: _t("Bcc") },
]

// useEmbeddedState is the documented way to persist a block's state back
// into data-embedded-props. Accessed via the namespace so a missing export
// on some build degrades instead of crashing the whole editor bundle.
const useEmbeddedState = embedUtils.useEmbeddedState
const getEmbeddedProps = embedUtils.getEmbeddedProps

export class EmbeddedEmailSendComponent extends Component {
  static template = "sanare_dms.EmbeddedEmailSend"
  static components = { AutoComplete, TagsList }
  static props = {
    host: { type: Object },
  }

  setup() {
    this.orm = useService("orm")
    this.notification = useService("notification")
    this.action = useService("action")

    // {subject, to, cc, bcc, lastSend}; to/cc/bcc are arrays of {id, name}.
    if (useEmbeddedState) {
      this.state = useEmbeddedState(this.props.host)
      this._persist = null
    } else {
      this.state = useState({
        subject: "", to: [], cc: [], bcc: [], lastSend: null,
        ...(getEmbeddedProps ? getEmbeddedProps(this.props.host) : {}),
      })
      this._persist = () => {
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
        this.props.host.dispatchEvent(new InputEvent("input", { bubbles: true }))
      }
    }
    this.ui = useState({ sending: false })
    this.inputs = useState({ to: "", cc: "", bcc: "" })
  }

  get rows() {
    return RECIPIENT_ROWS
  }

  list(field) {
    return this.state[field] || []
  }

  changed() {
    if (this._persist) {
      this._persist()
    }
  }

  // ---- recipients ----------------------------------------------------
  tagsFor(field) {
    return this.list(field).map((r) => ({
      id: r.id,
      text: r.name,
      onDelete: () => this.remove(field, r.id),
    }))
  }

  domainFor(field) {
    const chosen = this.list(field).map((r) => r.id)
    return chosen.length ? [["id", "not in", chosen]] : []
  }

  sourcesFor(field) {
    return [
      {
        options: async (request) => {
          const q = (request || "").trim()
          let opts = []
          if (q) {
            const pairs = await this.orm.call("res.partner", "name_search", [], {
              name: q,
              args: this.domainFor(field),
              operator: "ilike",
              limit: 8,
            })
            opts = pairs.map(([id, name]) => ({ label: name, partnerId: id, partnerName: name }))
            opts.push({ label: _t('Create "%s"', q), createName: q })
          }
          return opts
        },
      },
    ]
  }

  onInput(field, { inputValue }) {
    this.inputs[field] = inputValue
  }

  async onSelect(field, option) {
    this.inputs[field] = ""
    if (option.createName) {
      await this.addByCreate(field, option.createName)
    } else {
      this.addRecords(field, [{ id: option.partnerId, name: option.partnerName }])
    }
  }

  addRecords(field, records) {
    const existing = new Set(this.list(field).map((r) => r.id))
    const added = (records || [])
      .filter((r) => r && r.id && !existing.has(r.id))
      .map((r) => ({ id: r.id, name: r.name || r.display_name || _t("Contact") }))
    if (added.length) {
      this.state[field] = [...this.list(field), ...added]
      this.changed()
    }
  }

  async addByCreate(field, name) {
    const clean = (name || "").trim()
    if (!clean) {
      return
    }
    const [id, displayName] = await this.orm.call("res.partner", "name_create", [clean])
    this.addRecords(field, [{ id, name: displayName }])
  }

  remove(field, id) {
    this.state[field] = this.list(field).filter((r) => r.id !== id)
    this.changed()
  }

  // ---- subject -----------------------------------------------------
  onSubjectInput(ev) {
    this.state.subject = ev.target.value
    this.changed()
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
    // Fallback for when the form model isn't on this sub-env.
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
      // Persist the block (and get a real resId) first - the server's
      // sendable gate checks the stored content_html.
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
      this.changed()
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
