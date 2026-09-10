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
    this.state = useState({ failed: false })

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
