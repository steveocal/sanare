/** @odoo-module **/

import { Component, useState, useRef } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

// Curated, deliberately short list - Odoo doesn't guarantee every view type
// is actually defined for whatever model gets picked here, so this only
// offers the types most models define. odoo_view_field.js's own VIEW_LABELS
// is a display-only list (it only ever shows a type that already rendered,
// via capture) - not reused here since the two lists serve different risk
// profiles.
const VIEW_TYPE_CHOICES = [
    ["list", _t("List"), "fa-list-ul"],
    ["kanban", _t("Kanban"), "fa-th-large"],
    ["form", _t("Form"), "fa-dashboard"],
    ["calendar", _t("Calendar"), "fa-calendar"],
    ["pivot", _t("Pivot"), "fa-table"],
    ["graph", _t("Graph"), "fa-bar-chart"],
    ["activity", _t("Activity"), "fa-clock-o"],
];

/* Selection-only recursive tree node for the New Document picker - a
 * stripped-down sibling of DmsTreeNode (dms_browser.js): expand/collapse and
 * click-to-select only, no drag/drop, no per-row "+"/delete actions. Only
 * containers (folders/HTML/Markdown pages) are shown - a leaf document is
 * never a valid place to create something inside. Shares the *same* node
 * objects and expandedIds as the main sidebar tree (passed down from
 * DmsBrowser as props), so expand state stays in sync between the two and
 * no folder data is ever fetched twice. */
export class DmsPickerTreeNode extends Component {
    static template = "sanare_dms.DmsPickerTreeNode";
    static props = ["*"];

    get childContainers() {
        return (this.props.node.children || []).filter((c) => c.can_have_children);
    }
}
DmsPickerTreeNode.components = { DmsPickerTreeNode };

export class DmsNewDocumentDialog extends Component {
    static template = "sanare_dms.DmsNewDocumentDialog";
    static components = { Dialog, DmsPickerTreeNode };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.fileInputRef = useRef("fileInput");
        this.state = useState({
            step: "tiles", // "tiles" | "odoo_view"
            selectedFolderId: this.props.initialParentId || false,
            modelQuery: "",
            modelResults: [],
            selectedModel: null, // { id, name, model }
        });
        this._modelSearchSeq = 0;
    }

    get containerTree() {
        return (this.props.tree || []).filter((n) => n.can_have_children);
    }

    // Finds the selected node anywhere in the (possibly not-fully-expanded)
    // tree - null for the root ("Documents", id === false), which has no
    // node of its own.
    get selectedNode() {
        if (!this.state.selectedFolderId) {
            return null;
        }
        const find = (nodes) => {
            for (const n of nodes || []) {
                if (n.id === this.state.selectedFolderId) {
                    return n;
                }
                const inChildren = find(n.children);
                if (inChildren) {
                    return inChildren;
                }
            }
            return null;
        };
        return find(this.props.tree);
    }

    get selectedFolderName() {
        return this.selectedNode ? this.selectedNode.name : _t("Documents");
    }

    // Office Documents (and anything upload-based, since those are Office
    // Documents too) can only be created directly inside a folder, never
    // nested inside an HTML/Markdown page - mirrors newTypesFor's own rule
    // in dms_browser.js (the model's _check_container_integrity
    // constraint). The root ("Documents", no node) counts as a folder.
    get officeAllowed() {
        const ct = this.selectedNode ? this.selectedNode.content_type : "folder";
        return (ct || "folder") === "folder";
    }

    get viewTypeChoices() {
        return VIEW_TYPE_CHOICES;
    }

    // ---- folder tree ---------------------------------------------------
    selectFolder(id) {
        this.state.selectedFolderId = id || false;
    }

    // ---- simple tiles ---------------------------------------------------
    pick(type) {
        this.props.onCreate(type, this.state.selectedFolderId);
        this.props.close();
    }

    pickOffice(officeKind) {
        this.props.onCreate("onlyoffice", this.state.selectedFolderId, {
            default_office_kind: officeKind,
        });
        this.props.close();
    }

    pickTemplate() {
        this.props.onTemplate(this.state.selectedFolderId);
        this.props.close();
    }

    // ---- upload / PDF form ----------------------------------------------
    startUpload(accept) {
        const el = this.fileInputRef.el;
        if (!el) {
            return;
        }
        el.value = "";
        el.accept = accept;
        el.click();
    }

    onFileChosen(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        this.props.onUpload(this.state.selectedFolderId, file);
        this.props.close();
    }

    // ---- Odoo View: pick a model, then a view type -----------------------
    openOdooViewStep() {
        this.state.step = "odoo_view";
        this.state.selectedModel = null;
        this.state.modelQuery = "";
        this.state.modelResults = [];
    }

    backToTiles() {
        this.state.step = "tiles";
    }

    async onModelInput(ev) {
        const query = ev.target.value;
        this.state.modelQuery = query;
        this.state.selectedModel = null;
        const seq = ++this._modelSearchSeq;
        if (!query || query.length < 2) {
            this.state.modelResults = [];
            return;
        }
        let recs = [];
        try {
            recs = await this.orm.searchRead(
                "ir.model",
                [
                    ["transient", "=", false],
                    "|", ["name", "ilike", query], ["model", "ilike", query],
                ],
                ["id", "name", "model"],
                { limit: 8 }
            );
        } catch {
            recs = [];
        }
        if (seq !== this._modelSearchSeq) {
            return; // a newer keystroke's search already landed
        }
        this.state.modelResults = recs;
    }

    chooseModel(rec) {
        this.state.selectedModel = rec;
        this.state.modelQuery = `${rec.name} (${rec.model})`;
        this.state.modelResults = [];
    }

    pickOdooView(viewType) {
        const model = this.state.selectedModel;
        if (!model) {
            this.notification.add(_t("Choose a model first."), { type: "warning" });
            return;
        }
        const descriptor = {
            resModel: model.model,
            viewType,
            views: viewType === "form" ? [[false, "form"]] : [[false, viewType], [false, "search"]],
            domain: [],
            context: {},
            title: model.name,
        };
        this.props.onCreate("odoo_view", this.state.selectedFolderId, {
            default_view_descriptor: descriptor,
        });
        this.props.close();
    }
}
