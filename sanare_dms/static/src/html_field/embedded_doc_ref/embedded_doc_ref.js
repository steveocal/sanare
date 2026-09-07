/** @odoo-module **/

import { Component, useState, onWillStart, markup } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { _t } from "@web/core/l10n/translation"
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils"

export class EmbeddedDocRefComponent extends Component {
  static template = "sanare_dms.EmbeddedDocRef"
  static props = {
    host: { type: Object },
    documentId: { type: Number },
    documentName: { type: String, optional: true },
  }

  setup() {
    this.orm = useService("orm")
    this.action = useService("action")
    this.state = useState({
      loading: true,
      error: "",
      name: this.props.documentName || "",
      contentHtml: markup(""),
    })
    // Runs every time this document is opened (the embedded component
    // mounts fresh on every render of the host document, there is no
    // cached/frozen copy) - this is what keeps the embed "live".
    onWillStart(() => this.load())
  }

  async load() {
    this.state.error = ""
    try {
      const data = await this.orm.call("sanare.document", "get_embedded_content", [
        this.props.documentId,
      ])
      if (data.error === "not_found") {
        this.state.error = _t("This document no longer exists.")
      } else if (data.error === "unsupported_type") {
        this.state.error = _t("This document is no longer a web page and can't be embedded.")
      } else {
        this.state.name = data.name
        this.state.contentHtml = markup(data.content_html || "")
      }
    } catch {
      this.state.error = _t("This document is unavailable - it may have been removed, or you may no longer have access to it.")
    } finally {
      this.state.loading = false
    }
  }

  refresh() {
    this.state.loading = true
    this.load()
  }

  openDocument() {
    this.action.doAction({
      type: "ir.actions.act_window",
      res_model: "sanare.document",
      res_id: this.props.documentId,
      views: [[false, "form"]],
      target: "current",
    })
  }
}

export const sanareDocRefEmbedding = {
  name: "sanareDocRef",
  Component: EmbeddedDocRefComponent,
  getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
}
