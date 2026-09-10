/** @odoo-module **/

import { Component, useSubEnv, useState, onError, onWillUnmount } from "@odoo/owl"
import { _t } from "@web/core/l10n/translation"
import { useService } from "@web/core/utils/hooks"
import * as embedUtils from "@html_editor/others/embedded_component_utils"
import { View } from "@web/views/view"

function readProps(host) {
  try {
    return embedUtils.getEmbeddedProps?.(host) || {}
  } catch {
    return {}
  }
}

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
}

// Mounts a real Odoo <View> with its search bar inside the document body,
// from the descriptor the "Save as View Template" cog action captured.
// onError() guards the mount so a failure degrades to a fallback link
// instead of crashing the editor. Persisted UI state (height, zoom, the
// picked view type) rides in data-embedded-props next to the descriptor.
export class EmbeddedViewComponent extends Component {
  static template = "sanare_dms.EmbeddedView"
  static components = { View }
  static props = { host: { type: Object } }

  setup() {
    this.action = useService("action")
    this.orm = useService("orm")
    this.d = readProps(this.props.host)
    this._saveTimer = null
    onWillUnmount(() => {
      if (this._saveTimer) {
        clearTimeout(this._saveTimer)
        this.saveState()
      }
    })
    this.state = useState({
      failed: false,
      height: this.d.height || null,
      zoom: this.d.zoom || 1,
      viewType: this.d.viewType,
    })

    useSubEnv({
      config: {
        actionType: "ir.actions.act_window",
        actionId: false,
        views: this.d.views || [],
        viewType: this.d.viewType,
        breadcrumbs: [],
        noBreadcrumbs: true,
        getDisplayName: () => this.d.title || this.d.resModel || "",
        setDisplayName: () => {},
        historyBack: () => {},
        historyForward: () => {},
      },
    })

    // Stable identities so <View> doesn't see "changed" callbacks each render.
    this._selectRecord = (resId) => this.openRecord(resId)
    this._createRecord = () => this.openRecord(false)
    this._searchModelStr = this.d.searchState
      ? typeof this.d.searchState === "string"
        ? this.d.searchState
        : JSON.stringify(this.d.searchState)
      : null
    this._views =
      this.d.views && this.d.views.length
        ? this.d.views
        : [[false, this.d.viewType], [false, "search"]]

    onError((error) => {
      console.warn("[sanare_dms] embedded view failed to mount", error)
      this.state.failed = true
    })
  }

  get ready() {
    return !this.state.failed && this.d && this.d.resModel && this.state.viewType
  }

  get viewProps() {
    // Cache per view type: only `type` ever changes, and t-key already
    // remounts <View> on that. Returning a stable object keeps zoom/resize
    // renders from re-rendering the whole view.
    if (!this._vp || this._vpType !== this.state.viewType) {
      this._vpType = this.state.viewType
      this._vp = {
        type: this.state.viewType,
        resModel: this.d.resModel,
        views: this._views,
        domain: this.d.domain || [],
        context: this.d.context || {},
        display: { controlPanel: {} },
        selectRecord: this._selectRecord,
        createRecord: this._createRecord,
        noContentHelp: _t("No records match this view template."),
        ...(this._searchModelStr
          ? { globalState: { searchModel: this._searchModelStr } }
          : {}),
      }
    }
    return this._vp
  }

  get switchableTypes() {
    const types = []
    for (const entry of this.d.views || []) {
      const t = entry && entry[1]
      if (t && t !== "search" && t !== "form" && !types.includes(t)) {
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

  get bodyStyle() {
    return this.state.height ? `height:${this.state.height}px` : ""
  }

  get zoomPct() {
    return Math.round(this.state.zoom * 100) + "%"
  }

  // ---- persisted UI state --------------------------------------
  persist() {
    try {
      this.props.host.setAttribute(
        "data-embedded-props",
        JSON.stringify({
          ...this.d,
          height: this.state.height || undefined,
          zoom: this.state.zoom,
          viewType: this.state.viewType,
        })
      )
      const editable = this.props.host.closest(".odoo-editor-editable")
      ;(editable || this.props.host).dispatchEvent(new Event("input", { bubbles: true }))
    } catch {
      // The save path re-reads the DOM anyway.
    }
    // Also persist server-side (debounced) so zoom / size / view stick
    // even without a manual form save.
    clearTimeout(this._saveTimer)
    this._saveTimer = setTimeout(() => this.saveState(), 800)
  }

  async saveState() {
    this._saveTimer = null
    const documentId = this.env.model?.root?.resId
    if (!documentId) {
      return
    }
    try {
      await this.orm.call("sanare.document", "save_view_block_state", [
        documentId,
        {
          zoom: this.state.zoom,
          height: this.state.height || undefined,
          viewType: this.state.viewType,
        },
      ])
    } catch {
      // setAttribute already kept the DOM current for a form save.
    }
  }

  setViewType(t) {
    if (t && t !== this.state.viewType) {
      this.state.viewType = t
      this.persist()
    }
  }

  setZoom(z) {
    const clamped = Math.min(2, Math.max(0.5, Math.round(z * 10) / 10))
    if (clamped !== this.state.zoom) {
      this.state.zoom = clamped
      this.persist()
    }
  }

  zoomBy(delta) {
    this.setZoom(this.state.zoom + delta)
  }

  // The body has `resize: vertical` (a drag grip). Only persist when the
  // height actually changed between mousedown and mouseup - a plain click
  // on a row/filter must not pin the height or dirty the document.
  onBodyMouseDown(ev) {
    this._h0 = Math.round(ev.currentTarget.getBoundingClientRect().height)
  }

  onResize(ev) {
    const h = Math.round(ev.currentTarget.getBoundingClientRect().height)
    if (this._h0 && Math.abs(h - this._h0) > 1 && h !== this.state.height) {
      this.state.height = h
      this.persist()
    }
    this._h0 = null
  }

  // ---- navigation ---------------------------------------------
  openRecord(resId) {
    const action = {
      type: "ir.actions.act_window",
      res_model: this.d.resModel,
      views: [[false, "form"]],
      target: "current",
      context: this.d.context || {},
    }
    if (resId) {
      action.res_id = resId
    }
    this.action.doAction(action)
  }

  openInFull() {
    this.action.doAction({
      type: "ir.actions.act_window",
      name: this.d.title || this.d.resModel,
      res_model: this.d.resModel,
      views:
        this.d.views && this.d.views.length
          ? this.d.views
          : [[false, this.state.viewType], [false, "search"]],
      domain: this.d.domain || [],
      context: this.d.context || {},
      target: "current",
    })
  }
}

export const embeddedViewEmbedding = {
  name: "sanareView",
  Component: EmbeddedViewComponent,
  getProps: (host) => ({ host }),
}
