/** @odoo-module **/

import { registry } from "@web/core/registry"
import { Component } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { _t } from "@web/core/l10n/translation"
import { DropdownItem } from "@web/core/dropdown/dropdown_item"

// Context keys that only make sense in the originating action - they must
// not travel into the stored view template.
const TRANSIENT_CTX_KEYS = [
  "active_id",
  "active_ids",
  "active_model",
  "params",
  "view_type",
  "default_",
]

function cleanContext(ctx) {
  const out = {}
  for (const [k, v] of Object.entries(ctx || {})) {
    if (TRANSIENT_CTX_KEYS.some((p) => (p.endsWith("_") ? k.startsWith(p) : k === p))) {
      continue
    }
    out[k] = v
  }
  return out
}

export class SanareViewToTemplate extends Component {
  static template = "sanare_dms.ViewToTemplateItem"
  static components = { DropdownItem }
  static props = {}

  setup() {
    this.orm = useService("orm")
    this.action = useService("action")
    this.notification = useService("notification")
  }

  async save() {
    const sm = this.env.searchModel
    const cfg = this.env.config || {}
    let searchState = null
    try {
      searchState = sm.exportState ? sm.exportState() : null
    } catch {
      searchState = null
    }
    const descriptor = {
      resModel: sm.resModel,
      viewType: cfg.viewType,
      views: cfg.views || [],
      domain: sm.domain || [],
      context: cleanContext(sm.context),
      searchState,
      title:
        (cfg.getDisplayName && cfg.getDisplayName()) ||
        cfg.displayName ||
        sm.resModel,
    }
    try {
      const res = await this.orm.call("sanare.document", "create_view_template", [
        descriptor,
      ])
      if (res && res.action) {
        this.action.doAction(res.action)
      }
    } catch (e) {
      this.notification.add(_t("Could not create the view template."), { type: "danger" })
      throw e
    }
  }
}

export const sanareViewToTemplateItem = {
  Component: SanareViewToTemplate,
  groupNumber: 20,
  isDisplayed: (env) =>
    Boolean(env.searchModel) &&
    Boolean(env.config && env.config.viewType) &&
    env.config.viewType !== "form",
}

registry.category("cogMenu").add("sanare-view-to-template", sanareViewToTemplateItem)
