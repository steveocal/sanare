/** @odoo-module **/

import { Component, useSubEnv, useState, onError } from "@odoo/owl"
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

// Mounts a real Odoo <View> (list/kanban/pivot/graph/...) with its search
// bar inside the document body, driven by the descriptor the "Save as View
// Template" cog action captured. onError() guards the mount so a <View>
// failure degrades to a fallback link instead of crashing the editor.
export class EmbeddedViewComponent extends Component {
  static template = "sanare_dms.EmbeddedView"
  static components = { View }
  static props = { host: { type: Object } }

  setup() {
    this.action = useService("action")
    this.d = readProps(this.props.host)
    this.state = useState({ failed: false, height: this.d.height || null })

    // <View> reads env.config (view switcher, breadcrumbs). Give it a
    // minimal standalone config so it can mount outside an action window.
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

    this.viewProps = {
      type: this.d.viewType,
      resModel: this.d.resModel,
      views:
        this.d.views && this.d.views.length
          ? this.d.views
          : [[false, this.d.viewType], [false, "search"]],
      domain: this.d.domain || [],
      context: this.d.context || {},
      display: { controlPanel: {} },
      // The standalone mount has no action to fall back on, so wire New and
      // row-click to open a full form ourselves; delete/multi-edit work
      // in-place in the list and need nothing.
      selectRecord: (resId) => this.openRecord(resId),
      createRecord: () => this.openRecord(false),
      noContentHelp: _t("No records match this view template."),
      // <View>/WithSearch expects globalState.searchModel to be a JSON
      // *string* (it JSON.parse()s it), not the exportState() object.
      ...(this.d.searchState
        ? {
            globalState: {
              searchModel:
                typeof this.d.searchState === "string"
                  ? this.d.searchState
                  : JSON.stringify(this.d.searchState),
            },
          }
        : {}),
    }

    onError((error) => {
      console.warn("[sanare_dms] embedded view failed to mount", error)
      this.state.failed = true
    })
  }

  get ready() {
    return !this.state.failed && this.d && this.d.resModel && this.d.viewType
  }

  get bodyStyle() {
    return this.state.height ? `height:${this.state.height}px` : ""
  }

  // The body has `resize: vertical` (a drag grip). Persist the height the
  // user dragged to into data-embedded-props so it survives reopen / a
  // "New from Template" copy.
  onResize(ev) {
    const h = Math.round(ev.currentTarget.getBoundingClientRect().height)
    if (h && h !== this.state.height) {
      this.state.height = h
      try {
        this.props.host.setAttribute(
          "data-embedded-props",
          JSON.stringify({ ...this.d, height: h })
        )
        const editable = this.props.host.closest(".odoo-editor-editable")
        ;(editable || this.props.host).dispatchEvent(new Event("input", { bubbles: true }))
      } catch {
        // The save path re-reads the DOM anyway.
      }
    }
  }

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
          : [[false, this.d.viewType], [false, "search"]],
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
