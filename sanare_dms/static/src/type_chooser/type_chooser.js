/** @odoo-module **/

import { Component, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";

const MODEL = "sanare.document";

// Curated, deliberately short list - kept in sync with VIEW_TYPES in
// dms_document.py. Odoo doesn't guarantee every view type exists for every
// model, so this only offers the types most models actually define.
const VIEW_TYPE_CHOICES = [
    ["list", _t("List"), "fa-list-ul"],
    ["kanban", _t("Kanban"), "fa-th-large"],
    ["form", _t("Form"), "fa-dashboard"],
    ["calendar", _t("Calendar"), "fa-calendar"],
    ["pivot", _t("Pivot"), "fa-table"],
    ["graph", _t("Graph"), "fa-bar-chart"],
    ["activity", _t("Activity"), "fa-clock-o"],
];

// Standard-layout replacement for the old "New Document" popup dialog: a
// field widget bound to type_chosen, embedded straight in the sheet where
// the real content editor (content_html/content_markdown/office_group/...)
// would otherwise render. Picking a tile just calls record.update() like
// any other widget - nothing is created server-side until the form itself
// is saved, exactly like typing into any other field of a new record.
// "From Template" and "Odoo View" are the two exceptions that do need a
// real record to point at (an existing template to copy, an existing
// record to reference) - both reuse SelectCreateDialog, the same standard
// Odoo record picker already used elsewhere in this module (dms_browser.js),
// not a custom popup.
export class DmsTypeChooser extends Component {
    static template = "sanare_dms.DmsTypeChooser";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.fileInputRef = useRef("fileInput");
        this.state = useState({
            // Set once a model + a specific record of that model have both
            // been picked for "Odoo View" - {modelId, modelName, modelDisplay,
            // resId, recordDisplay} - while set, the template shows the
            // view-type tiles instead of the main grid.
            pendingOdooView: null,
        });
    }

    get record() {
        return this.props.record;
    }

    get parentId() {
        const p = this.record.data.parent_id;
        return p ? p.id : false;
    }

    get hasOfficeKind() {
        return "office_kind" in this.record.fields;
    }

    // ---- simple tiles ---------------------------------------------------
    pick(type) {
        this.record.update({ content_type: type, type_chosen: true });
    }

    pickOffice(officeKind) {
        const vals = { content_type: "onlyoffice", type_chosen: true };
        if (this.hasOfficeKind) {
            vals.office_kind = officeKind;
        }
        this.record.update(vals);
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

    async onFileChosen(ev) {
        const file = ev.target.files && ev.target.files[0];
        if (!file) {
            return;
        }
        let base64;
        try {
            base64 = await this._fileToBase64(file);
        } catch {
            this.notification.add(_t("Could not read this file."), { type: "danger" });
            return;
        }
        this.record.update({
            content_type: "onlyoffice",
            file_content: base64,
            file_name: file.name,
            type_chosen: true,
        });
    }

    _fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve((reader.result || "").split(",")[1] || "");
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
        });
    }

    // ---- from template ----------------------------------------------------
    // Needs a real create() (template.copy()) - discards this unsaved draft
    // and navigates to the real copy instead.
    pickTemplate() {
        this.dialog.add(SelectCreateDialog, {
            resModel: MODEL,
            title: _t("New from Template"),
            domain: [["is_template", "=", true]],
            multiSelect: false,
            noCreate: true,
            onSelected: async (resIds) => {
                if (!resIds?.length) {
                    return;
                }
                let newId;
                try {
                    newId = await this.orm.call(MODEL, "browser_create_from_template", [
                        resIds[0], this.parentId,
                    ]);
                } catch (err) {
                    const msg =
                        (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        _t("Could not create a document from this template.");
                    this.notification.add(msg, { type: "danger" });
                    return;
                }
                await this.record.discard();
                this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: MODEL,
                    res_id: newId,
                    views: [[false, "form"]],
                    target: "current",
                });
            },
        });
    }

    // ---- Odoo View: pick a model, then look up one fixed record ----------
    pickOdooViewModel() {
        this.dialog.add(SelectCreateDialog, {
            resModel: "ir.model",
            title: _t("Choose a Model"),
            domain: [["transient", "=", false]],
            multiSelect: false,
            noCreate: true,
            onSelected: async (resIds) => {
                if (!resIds?.length) {
                    return;
                }
                const [modelRec] = await this.orm.read("ir.model", resIds, ["name", "model"]);
                this.lookupOdooViewRecord(resIds[0], modelRec.model, modelRec.name);
            },
        });
    }

    // "Lookup should occur after model selection" - this dialog only opens
    // once a model is already chosen, scoped to that model, and only ever
    // lets you pick an EXISTING record (noCreate) - the "reference a fixed
    // record" flow this whole tile is for.
    lookupOdooViewRecord(modelId, modelName, modelDisplay) {
        this.dialog.add(SelectCreateDialog, {
            resModel: modelName,
            title: _t("Choose a %s Record", modelDisplay),
            multiSelect: false,
            noCreate: true,
            onSelected: async (resIds) => {
                if (!resIds?.length) {
                    return;
                }
                const [rec] = await this.orm.read(modelName, resIds, ["display_name"]);
                this.state.pendingOdooView = {
                    modelId,
                    modelName,
                    modelDisplay,
                    resId: resIds[0],
                    recordDisplay: rec.display_name,
                };
            },
        });
    }

    cancelOdooView() {
        this.state.pendingOdooView = null;
    }

    get viewTypeChoices() {
        return VIEW_TYPE_CHOICES;
    }

    pickOdooViewType(viewType) {
        const p = this.state.pendingOdooView;
        if (!p) {
            return;
        }
        this.record.update({
            content_type: "odoo_view",
            view_model_id: { id: p.modelId, display_name: p.modelDisplay },
            view_res_id: p.resId,
            view_type: viewType,
            type_chosen: true,
        });
        this.state.pendingOdooView = null;
    }
}

export const dmsTypeChooser = {
    component: DmsTypeChooser,
};

registry.category("fields").add("sanare_type_chooser", dmsTypeChooser);
