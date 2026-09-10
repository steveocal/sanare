/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import {
    Component, useState, useChildSubEnv, useEffect, useRef, onMounted, useExternalListener,
} from "@odoo/owl";

const MODEL = "sanare.document";
const NEW_TYPES = [
    ["folder", _t("Folder")],
    ["html", _t("Web Page (HTML)")],
    ["knowledge_html", _t("Knowledge Page")],
    ["markdown", _t("Markdown")],
    ["onlyoffice", _t("Office Document")],
];

/* ------------------------------------------------------------------ *
 *  Recursive folder-tree node
 * ------------------------------------------------------------------ */
export class DmsTreeNode extends Component {
    static template = "sanare_dms.DmsTreeNode";
    static props = ["*"];

    get dms() {
        return this.env.dms;
    }
    get isSelected() {
        return this.env.dms.state.selectedId === this.props.node.id;
    }
    get isDragOver() {
        return this.env.dms.state.dragOverId === this.props.node.id;
    }
    get icon() {
        return this.env.dms.iconFor(this.props.node);
    }
}
DmsTreeNode.components = { DmsTreeNode, Dropdown, DropdownItem };

/* ------------------------------------------------------------------ *
 *  Main client action
 * ------------------------------------------------------------------ */
export class DmsBrowser extends Component {
    static template = "sanare_dms.DmsBrowser";
    static components = { DmsTreeNode, Dropdown, DropdownItem };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.expandedIds = new Set();
        this.dragIds = [];

        this.state = useState({
            tree: [],
            selectedId: false, // false === the "Documents" root
            // "folder" (normal tree browsing, right pane shows state.records
            // for state.selectedId) or "templates" (right pane shows the
            // flat state.templates list instead) - orthogonal to
            // selectedId, which folder browsing keeps using independently
            // so switching back to "folder" mode returns to where you were.
            viewMode: "folder",
            // content_type of the folder/HTML/Markdown page currently open
            // in the flat pane, or false for the root - drives which "New
            // Document" types are offered (Office Documents only inside a
            // folder, never nested inside another document).
            containerContentType: false,
            breadcrumb: [],
            records: [],
            templates: [],
            loadingTemplates: false,
            templatesDragOver: false,
            selection: new Set(),
            loadingTree: true,
            loadingList: true,
            dragOverId: null,
            creatingFolder: false,
            newFolderName: "",
            clipboard: { ids: [], names: [] },
        });

        this.newFolderInput = useRef("newFolderInput");
        useEffect(
            (el) => {
                if (el) {
                    el.focus();
                }
            },
            () => [this.newFolderInput.el]
        );

        // shared with the recursive DmsTreeNode instances via sub-env
        useChildSubEnv({
            dms: {
                state: this.state,
                iconFor: (node) => this.iconFor(node),
                toggle: (n) => this.toggleNode(n),
                select: (id) => this.selectFolder(id),
                open: (id) => this.openDocument(id),
                newDocument: (type, parentId) => this.newDocument(type, parentId),
                openTemplatePicker: (parentId) => this.openTemplatePicker(parentId),
                newTypesFor: (contentType) => this.newTypesFor(contentType),
                deleteRecord: (rec, ev) => this.deleteRecord(rec, ev),
                // onItemDragStart only ever reads rec.id - the node itself
                // (folder or leaf document) is all it needs.
                dragStart: (node, ev) => this.onItemDragStart(node, ev),
                dragOver: (id, ev) => this.onFolderDragOver(id, ev),
                dragLeave: () => this.onFolderDragLeave(),
                drop: (id, ev) => this.onFolderDrop(id, ev),
            },
        });

        // Load after mount (not in onWillStart) so the shell + loading states
        // render immediately even if the backend/network is slow.
        onMounted(() => {
            this.refreshTree();
            this.loadContents(false);
            this.loadTemplates();
        });

        // Ctrl/Cmd+C / Ctrl/Cmd+V, ignored while typing in an input/textarea
        // (the new-folder-name field, most relevantly) so this doesn't
        // fight with normal copy/paste of text.
        useExternalListener(window, "keydown", (ev) => {
            const tag = ev.target && ev.target.tagName;
            if (tag === "INPUT" || tag === "TEXTAREA") {
                return;
            }
            if ((ev.ctrlKey || ev.metaKey) && ev.key === "c") {
                this.copySelection();
            } else if ((ev.ctrlKey || ev.metaKey) && ev.key === "v") {
                this.pasteClipboard();
            }
        });
    }

    // ---- data --------------------------------------------------------
    async buildBranch(parentId) {
        const raw = await this.orm.call(MODEL, "browser_tree_children", [parentId || false]);
        const nodes = [];
        for (const f of raw) {
            const expanded = f.can_have_children && this.expandedIds.has(f.id);
            nodes.push({
                ...f,
                expanded,
                loading: false,
                // Leaf items (folders, HTML/Markdown pages and Office
                // Documents all included - can_have_children is false for
                // Office Documents and for empty containers) never recurse.
                children:
                    expanded && f.has_children ? await this.buildBranch(f.id) : null,
            });
        }
        return nodes;
    }

    async refreshTree() {
        this.state.loadingTree = true;
        try {
            this.state.tree = await this.buildBranch(false);
        } catch (err) {
            this.state.tree = [];
            this.notification.add(_t("Could not load folders."), { type: "danger" });
        } finally {
            this.state.loadingTree = false;
        }
    }

    async loadContents(folderId) {
        this.state.loadingList = true;
        this.state.selectedId = folderId || false;
        this.state.selection = new Set();
        try {
            const res = await this.orm.call(MODEL, "browser_contents", [folderId || false]);
            this.state.breadcrumb = res.breadcrumb;
            this.state.records = res.records;
            this.state.containerContentType = res.container_content_type || false;
        } catch (err) {
            this.state.breadcrumb = [];
            this.state.records = [];
            this.state.containerContentType = false;
            this.notification.add(_t("Could not load this folder."), { type: "danger" });
        } finally {
            this.state.loadingList = false;
        }
    }

    async toggleNode(node) {
        if (!node.can_have_children) {
            // Leaf documents (and Office Documents, which can never
            // contain anything) have no caret in the template, but guard
            // here too in case this is ever reached another way.
            return;
        }
        if (node.expanded) {
            node.expanded = false;
            this.expandedIds.delete(node.id);
            return;
        }
        node.expanded = true;
        this.expandedIds.add(node.id);
        if (node.children === null && node.has_children) {
            node.loading = true;
            node.children = await this.buildBranch(node.id);
            node.loading = false;
        }
    }

    selectFolder(folderId) {
        this.state.viewMode = "folder";
        this.loadContents(folderId || false);
    }

    // ---- templates section -------------------------------------------
    selectTemplates() {
        this.state.viewMode = "templates";
        this.state.selection = new Set();
        this.loadTemplates();
    }

    async loadTemplates() {
        this.state.loadingTemplates = true;
        try {
            this.state.templates = await this.orm.call(MODEL, "browser_templates", []);
        } catch (err) {
            this.state.templates = [];
            this.notification.add(_t("Could not load templates."), { type: "danger" });
        } finally {
            this.state.loadingTemplates = false;
        }
    }

    // ---- open / navigate -------------------------------------------
    onRowClick(rec, ev) {
        if (ev.ctrlKey || ev.metaKey) {
            const sel = new Set(this.state.selection);
            sel.has(rec.id) ? sel.delete(rec.id) : sel.add(rec.id);
            this.state.selection = sel;
        } else {
            this.state.selection = new Set([rec.id]);
        }
    }

    refresh() {
        this.refreshTree();
        this.loadContents(this.state.selectedId);
    }

    onNewFolderKeydown(ev) {
        if (ev.key === "Enter") {
            this.confirmNewFolder();
        } else if (ev.key === "Escape") {
            this.cancelNewFolder();
        }
    }

    onRowDblClick(rec) {
        if (rec.is_folder) {
            this.selectFolder(rec.id);
        } else {
            this.openDocument(rec.id);
        }
    }

    openDocument(resId) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: MODEL,
                res_id: resId,
                views: [[false, "form"]],
                target: "current",
            },
            { onClose: () => this.loadContents(this.state.selectedId) }
        );
    }

    // ---- drag & drop ---------------------------------------------
    onItemDragStart(rec, ev) {
        const sel = this.state.selection;
        this.dragIds = sel.has(rec.id) ? [...sel] : [rec.id];
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", this.dragIds.join(","));
    }

    onFolderDragOver(folderId, ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        this.state.dragOverId = folderId === false ? "root" : folderId;
    }

    onFolderDragLeave() {
        this.state.dragOverId = null;
    }

    async onFolderDrop(folderId, ev) {
        ev.preventDefault();
        this.state.dragOverId = null;
        const target = folderId || false;
        const ids = this.dragIds.filter((id) => id !== target);
        this.dragIds = [];
        if (!ids.length) {
            return;
        }
        try {
            await this.orm.call(MODEL, "browser_move", [ids, target]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("The move was rejected.");
            this.notification.add(msg, { type: "danger" });
        }
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    // Dropping onto the Templates section tags, it doesn't reparent - the
    // dragged item(s) keep their real folder location, same distinction
    // is_template's own help text draws.
    onTemplatesDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        this.state.templatesDragOver = true;
    }

    onTemplatesDragLeave() {
        this.state.templatesDragOver = false;
    }

    async onTemplatesDrop(ev) {
        ev.preventDefault();
        this.state.templatesDragOver = false;
        const ids = this.dragIds;
        this.dragIds = [];
        if (!ids.length) {
            return;
        }
        try {
            await this.orm.call(MODEL, "browser_set_template", [ids, true]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not tag as a template.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        this.notification.add(
            ids.length === 1 ? _t("Tagged as a template.") : _t("Tagged %s items as templates.", ids.length),
            { type: "info" }
        );
        await Promise.all([
            this.loadTemplates(),
            this.state.viewMode === "folder" ? this.loadContents(this.state.selectedId) : null,
        ]);
    }

    async toggleIsTemplate(rec, ev) {
        ev.stopPropagation();
        const value = !rec.is_template;
        try {
            await this.orm.call(MODEL, "browser_set_template", [[rec.id], value]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not change the template flag.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        rec.is_template = value;
        this.loadTemplates();
    }

    // ---- create ---------------------------------------------------
    startNewFolder() {
        this.state.creatingFolder = true;
        this.state.newFolderName = "";
    }

    cancelNewFolder() {
        this.state.creatingFolder = false;
    }

    async confirmNewFolder() {
        const name = this.state.newFolderName.trim();
        this.state.creatingFolder = false;
        if (!name) {
            return;
        }
        await this.orm.call(MODEL, "browser_create_folder", [
            name,
            this.state.selectedId || false,
        ]);
        if (this.state.selectedId) {
            this.expandedIds.add(this.state.selectedId);
        }
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    // Office Documents can only be created directly inside a folder, never
    // nested inside an HTML/Markdown page - mirrors the model's
    // _check_onlyoffice_containment constraint. "Folder" itself is never
    // offered here since these dropdowns are all "add a *document*" menus;
    // new folders are created via the toolbar's dedicated button.
    newTypesFor(parentContentType) {
        return NEW_TYPES.filter((nt) => {
            if (nt[0] === "folder") {
                return false;
            }
            if (nt[0] === "onlyoffice") {
                return (parentContentType || "folder") === "folder";
            }
            return true;
        });
    }

    // parentId lets a tree row's own "+" target that folder directly,
    // regardless of which folder is currently open in the flat pane -
    // defaults to the currently selected folder (the toolbar's own "New
    // Document" button calls this with no parentId).
    newDocument(type, parentId) {
        const targetParentId = parentId !== undefined ? parentId : (this.state.selectedId || false);
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: MODEL,
                views: [[false, "form"]],
                target: "current",
                context: {
                    default_parent_id: targetParentId,
                    default_content_type: type,
                    default_visibility_inherited: Boolean(targetParentId),
                },
            },
            {
                onClose: () => {
                    if (targetParentId) {
                        this.expandedIds.add(targetParentId);
                    }
                    return Promise.all([
                        this.refreshTree(),
                        this.loadContents(this.state.selectedId),
                    ]);
                },
            }
        );
    }

    // parentId same convention as newDocument - defaults to whatever's
    // currently selected in the folder tree.
    openTemplatePicker(parentId) {
        const targetParentId = parentId !== undefined ? parentId : (this.state.selectedId || false);
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
                        resIds[0], targetParentId,
                    ]);
                } catch (err) {
                    const msg =
                        (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        _t("Could not create a document from this template.");
                    this.notification.add(msg, { type: "danger" });
                    return;
                }
                if (targetParentId) {
                    this.expandedIds.add(targetParentId);
                }
                await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
                this.openDocument(newId);
            },
        });
    }

    // ---- delete -------------------------------------------------------
    deleteRecord(rec, ev) {
        ev.stopPropagation();
        this.dialog.add(ConfirmationDialog, {
            // Called for both flat-pane rows (which carry child_count) and
            // tree nodes (which carry has_children instead) - check either.
            title: _t("Delete"),
            body: rec.can_have_children && (rec.child_count || rec.has_children)
                ? _t(
                    "Delete “%s” and everything inside it? This cannot be undone.",
                    rec.name
                )
                : _t("Delete “%s”? This cannot be undone.", rec.name),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                try {
                    await this.orm.unlink(MODEL, [rec.id]);
                } catch (err) {
                    const msg =
                        (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        _t("Could not delete this item.");
                    this.notification.add(msg, { type: "danger" });
                    return;
                }
                if (this.state.selectedId === rec.id) {
                    // Deleted the folder we're currently looking inside of -
                    // neither browser_contents nor browser_tree_children
                    // return parent_id, so there's no "go up one level" id
                    // to navigate to here. Root is a safe, always-valid
                    // fallback rather than showing a now-deleted folder's
                    // stale contents.
                    this.selectFolder(false);
                }
                await Promise.all([
                    this.refreshTree(),
                    this.loadContents(this.state.selectedId),
                ]);
            },
            cancel: () => {},
        });
    }

    // ---- copy / paste -----------------------------------------------
    copySelection() {
        if (!this.state.selection.size) {
            return;
        }
        const ids = [...this.state.selection];
        const names = this.state.records
            .filter((r) => this.state.selection.has(r.id))
            .map((r) => r.name);
        this.state.clipboard = { ids, names };
        this.notification.add(
            names.length === 1
                ? _t("Copied “%s”.", names[0])
                : _t("Copied %s items.", names.length),
            { type: "info" }
        );
    }

    async pasteClipboard() {
        if (!this.state.clipboard.ids.length) {
            return;
        }
        const ids = this.state.clipboard.ids;
        try {
            await this.orm.call(MODEL, "browser_paste", [ids, this.state.selectedId || false]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("The paste was rejected.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        if (this.state.selectedId) {
            this.expandedIds.add(this.state.selectedId);
        }
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    // ---- ordering -----------------------------------------------------
    async reorder(recId, direction) {
        const ids = this.state.records.map((r) => r.id);
        const i = ids.indexOf(recId);
        const j = direction === "up" ? i - 1 : i + 1;
        if (i === -1 || j < 0 || j >= ids.length) {
            return;
        }
        [ids[i], ids[j]] = [ids[j], ids[i]];
        await this.orm.call(MODEL, "browser_reorder", [ids, this.state.selectedId || false]);
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    // ---- row actions ---------------------------------------------------
    async printDocument(rec, ev) {
        ev.stopPropagation();
        const action = await this.orm.call(MODEL, "action_report", [[rec.id]]);
        this.action.doAction(action);
    }

    downloadDocument(rec, ev) {
        ev.stopPropagation();
        window.open(`/sanare_dms/document/${rec.id}/download`, "_blank");
    }

    async togglePublish(rec, ev) {
        ev.stopPropagation();
        try {
            const isPublished = await this.orm.call(MODEL, "browser_toggle_publish", [[rec.id]]);
            rec.is_published = isPublished;
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not change publish status.");
            this.notification.add(msg, { type: "danger" });
        }
    }

    async toggleDisplayInPrint(rec, ev) {
        ev.stopPropagation();
        const value = !rec.display_in_print;
        await this.orm.write(MODEL, [rec.id], { display_in_print: value });
        rec.display_in_print = value;
    }

    iconFor(rec) {
        if (rec.is_folder) {
            return "fa-folder";
        }
        return {
            onlyoffice: "fa-file-word-o",
            html: "fa-file-code-o",
            knowledge_html: "fa-book",
            markdown: "fa-file-text-o",
        }[rec.content_type] || "fa-file-o";
    }

    stateClass(state) {
        return {
            draft: "text-bg-light",
            to_approve: "text-bg-warning",
            approved: "text-bg-success",
            rejected: "text-bg-danger",
        }[state] || "text-bg-light";
    }
}

registry.category("actions").add("sanare_dms.browser", DmsBrowser);
