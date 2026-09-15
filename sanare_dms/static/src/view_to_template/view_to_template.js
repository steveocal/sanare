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

// Pivot / graph config for server-side print. The reliable axis source is
// the search model's own groupBy (the graph X-axis and pivot rows both
// live there); mode / measure come from the view model's metaData when
// it's reachable, else the action context, else a default. Always write
// the key when the view type calls for it so print never falls back to
// the raw list. Only meaningful for search-based views (list/pivot/graph/
// ...), not the single-record form descriptor below.
function captureAggregateConfig(env, cfg, sm, descriptor) {
  const md = (env.model && env.model.metaData) || {}
  const ctx = cfg.context || {}
  const smGb = (sm.groupBy || []).map(String)
  if (cfg.viewType === "graph") {
    const mdGb = (md.groupBy || []).map(String)
    descriptor.graph = {
      mode: md.mode || ctx.graph_mode || "bar",
      measure: md.measure || ctx.graph_measure || "__count",
      groupBy: mdGb.length ? mdGb : smGb,
      stacked: !!md.stacked,
    }
  }
  if (cfg.viewType === "pivot") {
    const mdRows = (md.rowGroupBys || md.fullRowGroupBys || []).map(String)
    const mdCols = (md.colGroupBys || md.fullColGroupBys || []).map(String)
    const mdMeas = (md.activeMeasures || md.measures || []).map(String)
    descriptor.pivot = {
      rowGroupBys: mdRows.length ? mdRows : smGb,
      colGroupBys: mdCols,
      measures: mdMeas.length ? mdMeas : ["__count"],
    }
  }
}

// {resModel, viewType, views, domain, context, searchState, title[, graph|
// pivot]} from a search-based view (list/kanban/pivot/graph/calendar/...).
function buildSearchDescriptor(env) {
  const sm = env.searchModel
  const cfg = env.config || {}
  if (!sm) {
    return null
  }
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
      (cfg.getDisplayName && cfg.getDisplayName()) || cfg.displayName || sm.resModel,
  }
  captureAggregateConfig(env, cfg, sm, descriptor)
  return descriptor
}

// {resModel, viewType: "form", views, domain: [], context, resId, title}
// from a single-record dashboard form - no searchState (a form has no
// search bar) and a resId instead of a domain, since a form picks its
// record that way. This is what create_view_template's own action can't
// capture (see its isDisplayed below) and create_view_document exists for.
function buildFormDescriptor(env) {
  const cfg = env.config || {}
  const root = env.model && env.model.root
  if (!root || !root.resModel) {
    return null
  }
  return {
    resModel: root.resModel,
    viewType: "form",
    views: [[false, "form"]],
    domain: [],
    context: cleanContext(root.context || {}),
    resId: root.resId || undefined,
    title: (cfg.getDisplayName && cfg.getDisplayName()) || cfg.displayName || root.resModel,
  }
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
    const descriptor = buildSearchDescriptor(this.env)
    if (!descriptor) {
      this.notification.add(_t("Nothing to capture from this view."), { type: "warning" })
      return
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

// "Save as Odoo View Document" - the standalone counterpart above.
// Available from the same views as "Save as View Template" plus a
// single-record dashboard form, which the template item excludes since a
// form has no search state worth saving into an embedded block.
export class SanareViewToDocument extends Component {
  static template = "sanare_dms.ViewToDocumentItem"
  static components = { DropdownItem }
  static props = {}

  setup() {
    this.orm = useService("orm")
    this.action = useService("action")
    this.notification = useService("notification")
  }

  async save() {
    const cfg = this.env.config || {}
    const descriptor =
      cfg.viewType === "form" ? buildFormDescriptor(this.env) : buildSearchDescriptor(this.env)
    if (!descriptor) {
      this.notification.add(_t("Nothing to capture from this view."), { type: "warning" })
      return
    }
    try {
      const res = await this.orm.call("sanare.document", "create_view_document", [
        descriptor,
      ])
      if (res && res.action) {
        this.action.doAction(res.action)
      }
    } catch (e) {
      this.notification.add(_t("Could not create the Odoo View document."), { type: "danger" })
      throw e
    }
  }
}

export const sanareViewToDocumentItem = {
  Component: SanareViewToDocument,
  groupNumber: 20,
  isDisplayed: (env) => {
    const cfg = env.config || {}
    if (!cfg.viewType) {
      return false
    }
    if (cfg.viewType === "form") {
      return Boolean(env.model && env.model.root && env.model.root.resModel)
    }
    return Boolean(env.searchModel)
  },
}

registry.category("cogMenu").add("sanare-view-to-document", sanareViewToDocumentItem)
