/** @odoo-module **/

import { Component, useRef, useState, onError } from "@odoo/owl"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"
import { standardFieldProps } from "@web/views/fields/standard_field_props"
import { registry } from "@web/core/registry"
import { View } from "@web/views/view"

const VIEW_ICONS = {
  list: "fa-list-ul",
  kanban: "fa-th-large",
  pivot: "fa-table",
  graph: "fa-bar-chart",
  calendar: "fa-calendar",
  map: "fa-map-o",
  activity: "fa-clock-o",
  cohort: "fa-line-chart",
  gantt: "fa-tasks",
  hierarchy: "fa-sitemap",
  form: "fa-dashboard",
}
const VIEW_LABELS = {
  list: _t("List"),
  kanban: _t("Kanban"),
  pivot: _t("Pivot"),
  graph: _t("Graph"),
  calendar: _t("Calendar"),
  map: _t("Map"),
  activity: _t("Activity"),
  cohort: _t("Cohort"),
  gantt: _t("Gantt"),
  hierarchy: _t("Hierarchy"),
  form: _t("Dashboard"),
}

// Mounts a real Odoo <View> straight from the view_descriptor field of an
// odoo_view document - the standalone sibling of
// html_field/embedded_view/embedded_view.js, which mounts the same kind of
// descriptor from a data-embedded="sanareView" marker inside a Html field.
// No host-DOM/data-embedded-props round trip here since this is a real ORM
// field: reads/writes go straight through the record and RPCs, same as any
// other field widget.
export class OdooViewField extends Component {
  static template = "sanare_dms.OdooViewField"
  static components = { View }
  static props = { ...standardFieldProps }

  setup() {
    this.orm = useService("orm")
    this.action = useService("action")
    this.notification = useService("notification")
    this.captureRef = useRef("capture")
    this.state = useState({
      failed: false,
      viewType: this.descriptor.viewType,
      snapping: false,
      snapshotDate: null,
    })
    onError((error) => {
      console.warn("[sanare_dms] Odoo View field failed to mount", error)
      this.state.failed = true
    })
  }

  get descriptor() {
    return this.props.record.data[this.props.name] || {}
  }

  get ready() {
    return !this.state.failed && Boolean(this.descriptor.resModel) && Boolean(this.state.viewType)
  }

  get viewProps() {
    const d = this.descriptor
    const views =
      d.views && d.views.length ? d.views : [[false, this.state.viewType], [false, "search"]]
    const searchStateStr = d.searchState
      ? typeof d.searchState === "string"
        ? d.searchState
        : JSON.stringify(d.searchState)
      : null
    return {
      type: this.state.viewType,
      resModel: d.resModel,
      views,
      domain: d.domain || [],
      context: d.context || {},
      display: { controlPanel: {} },
      noContentHelp: _t("No records match this view."),
      ...(d.resId ? { resId: d.resId } : {}),
      ...(searchStateStr ? { globalState: { searchModel: searchStateStr } } : {}),
    }
  }

  get switchableTypes() {
    const d = this.descriptor
    const types = []
    for (const entry of d.views || []) {
      const t = entry && entry[1]
      if (t && t !== "search" && !types.includes(t)) {
        types.push(t)
      }
    }
    if (!types.includes(this.state.viewType)) {
      types.unshift(this.state.viewType)
    }
    return types.map((t) => ({
      type: t,
      label: VIEW_LABELS[t] || t,
      icon: VIEW_ICONS[t] || "fa-table",
    }))
  }

  get snapshotLabel() {
    if (this.state.snapping) {
      return _t("Capturing…")
    }
    if (this.state.snapshotDate) {
      return _t("Snapshot: %s", this.state.snapshotDate)
    }
    return this.props.record.data.view_snapshot_id
      ? _t("Snapshot saved")
      : _t("No print snapshot")
  }

  setViewType(t) {
    if (t && t !== this.state.viewType) {
      this.state.viewType = t
    }
  }

  openInFull() {
    const d = this.descriptor
    const action = {
      type: "ir.actions.act_window",
      name: d.title || d.resModel,
      res_model: d.resModel,
      views: d.views && d.views.length ? d.views : [[false, this.state.viewType]],
      domain: d.domain || [],
      context: d.context || {},
      target: "current",
    }
    if (d.resId) {
      action.res_id = d.resId
    }
    this.action.doAction(action)
  }

  async snapshot() {
    const el = this.captureRef.el
    const h2c = window.html2canvas
    const documentId = this.props.record.resId
    if (!el || !h2c || !documentId || this.state.snapping) {
      this.notification.add(_t("Can't snapshot this view."), { type: "warning" })
      return
    }
    this.state.snapping = true
    try {
      const canvas = await h2c(el, {
        backgroundColor: "#ffffff",
        scale: 2,
        useCORS: true,
        logging: false,
      })
      const png = canvas.toDataURL("image/png")
      const res = await this.orm.call("sanare.document", "save_view_snapshot", [
        documentId,
        { png },
      ])
      this.state.snapshotDate = res.date
      this.notification.add(_t("Snapshot saved for printing."), { type: "success" })
    } catch (e) {
      console.warn("[sanare_dms] view snapshot failed", e)
      this.notification.add(_t("Snapshot failed."), { type: "danger" })
    } finally {
      this.state.snapping = false
    }
  }
}

export const odooViewField = {
  component: OdooViewField,
  displayName: _t("Odoo View"),
  supportedTypes: ["json"],
}

registry.category("fields").add("sanare_odoo_view", odooViewField)
