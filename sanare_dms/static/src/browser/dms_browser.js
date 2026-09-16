/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { View } from "@web/views/view";
import {
    Component, useState, useChildSubEnv, useSubEnv, onMounted,
    useExternalListener, onError,
} from "@odoo/owl";

const MODEL = "sanare.document";
// Office Documents are one content_type covering several real file kinds -
// iconFor uses this to tell a Word doc from a Spreadsheet from a
// Presentation in the tree/list, instead of always showing a Word icon.
const OFFICE_ICONS = {
    doc: "fa-file-word-o", docx: "fa-file-word-o",
    xls: "fa-file-excel-o", xlsx: "fa-file-excel-o", csv: "fa-file-excel-o",
    ppt: "fa-file-powerpoint-o", pptx: "fa-file-powerpoint-o",
    pdf: "fa-file-pdf-o",
};

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
 *  Inline document editor for the detail pane
 *  Mounts the real sanare.document form view (so the sanare_html editor,
 *  its embedded blocks - email / view / doc-ref - and every field render
 *  and edit exactly as on the standalone form) inside a minimal
 *  standalone action config. onError degrades a mount failure to a link.
 * ------------------------------------------------------------------ */
export class DmsDocForm extends Component {
    static template = "sanare_dms.DmsDocForm";
    static components = { View };
    static props = { resId: Number, onSaved: { type: Function, optional: true } };

    setup() {
        this.state = useState({ failed: false });
        useSubEnv({
            config: {
                actionType: "ir.actions.act_window",
                actionId: false,
                views: [[false, "form"]],
                viewType: "form",
                breadcrumbs: [],
                noBreadcrumbs: true,
                getDisplayName: () => "",
                setDisplayName: () => {},
                historyBack: () => {},
                historyForward: () => {},
            },
        });
        onError((error) => {
            console.warn("[sanare_dms] inline form failed to mount", error);
            this.state.failed = true;
        });
    }

    get viewProps() {
        return {
            type: "form",
            resModel: "sanare.document",
            resId: this.props.resId,
            display: { controlPanel: {} },
            onSave: () => this.props.onSaved?.(),
            onDiscard: () => this.props.onSaved?.(),
        };
    }
}

/* ------------------------------------------------------------------ *
 *  Main client action
 * ------------------------------------------------------------------ */
export class DmsBrowser extends Component {
    static template = "sanare_dms.DmsBrowser";
    static components = { DmsTreeNode, DmsDocForm, Dropdown, DropdownItem };
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
            // detail pane: the selected non-folder document's rendered
            // content, or null when a folder is selected (pane shows the
            // contents list instead).
            detail: null,
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
            dragOverIsLink: false,
            clipboard: { ids: [], names: [] },
        });

        // shared with the recursive DmsTreeNode instances via sub-env
        useChildSubEnv({
            dms: {
                state: this.state,
                iconFor: (node) => this.iconFor(node),
                toggle: (n) => this.toggleNode(n),
                select: (id) => this.select(id),
                open: (id) => this.openDocument(id),
                newDocument: (type, parentId) => this.newDocument(type, parentId),
                newArticle: (parentId) => this.createBlankDocument(parentId),
                openTemplatePicker: (parentId) => this.openTemplatePicker(parentId),
                goToRealLocation: (rec, ev) => this.goToRealLocation(rec, ev),
                deleteRecord: (rec, ev) => this.deleteRecord(rec, ev),
                restoreRecord: (rec, ev) => this.restoreRecord(rec, ev),
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
        this.select(folderId || false);
    }

    // Tree selection: any node - folder or leaf document. loadContents gives
    // the breadcrumb (+ children list for a container); loadDetail gives the
    // document body for a leaf, or null for a folder.
    select(id) {
        this.state.viewMode = "folder";
        this.loadContents(id || false);
        this.loadDetail(id || false);
    }

    async loadDetail(id) {
        if (!id) {
            this.state.detail = null;
            return;
        }
        try {
            const d = await this.orm.call(MODEL, "browser_detail", [id]);
            // A folder has no detail form - the pane keeps showing its list.
            this.state.detail = d && !d.is_folder ? d : null;
        } catch {
            this.state.detail = null;
        }
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

    // ---- selection (checkbox column + central Actions menu) -----------
    toggleRowSelection(rec, ev) {
        ev.stopPropagation();
        const sel = new Set(this.state.selection);
        sel.has(rec.id) ? sel.delete(rec.id) : sel.add(rec.id);
        this.state.selection = sel;
    }

    toggleSelectAll(ev) {
        ev.stopPropagation();
        this.state.selection = this.allSelected
            ? new Set()
            : new Set(this.state.records.map((r) => r.id));
    }

    get allSelected() {
        return this.state.records.length > 0 &&
            this.state.records.every((r) => this.state.selection.has(r.id));
    }

    get selectedRecords() {
        return this.state.records.filter((r) => this.state.selection.has(r.id));
    }

    get singleSelected() {
        const recs = this.selectedRecords;
        return recs.length === 1 ? recs[0] : null;
    }

    get anySelectedAreLinks() {
        return this.selectedRecords.some((r) => r.is_link);
    }

    get allSelectedAreLinks() {
        const recs = this.selectedRecords;
        return recs.length > 0 && recs.every((r) => r.is_link);
    }

    get allSelectedInTrash() {
        const recs = this.selectedRecords;
        return recs.length > 0 && recs.every((r) => r.in_trash);
    }

    async bulkRestore() {
        const ids = [...this.state.selection];
        try {
            await this.orm.call(MODEL, "browser_restore", [ids]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not restore these items.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        this.notification.add(_t("Restored %s items.", ids.length), { type: "info" });
        this.state.selection = new Set();
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    refresh() {
        this.refreshTree();
        this.loadContents(this.state.selectedId);
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
        // Ctrl/Cmd held while dragging = link instead of move - dropEffect
        // and the drop-target style (dashed teal vs. solid purple, see
        // o_dms_drop_target_link) both reflect it live as the modifier key
        // is pressed/released mid-drag, so the outcome is never a surprise
        // at drop time.
        const isLink = ev.ctrlKey || ev.metaKey;
        ev.dataTransfer.dropEffect = isLink ? "link" : "move";
        this.state.dragOverId = folderId === false ? "root" : folderId;
        this.state.dragOverIsLink = isLink;
    }

    onFolderDragLeave() {
        this.state.dragOverId = null;
        this.state.dragOverIsLink = false;
    }

    async onFolderDrop(folderId, ev) {
        ev.preventDefault();
        const isLink = ev.ctrlKey || ev.metaKey;
        this.state.dragOverId = null;
        this.state.dragOverIsLink = false;
        const target = folderId || false;
        const ids = this.dragIds.filter((id) => id !== target);
        this.dragIds = [];
        if (!ids.length) {
            return;
        }
        try {
            if (isLink) {
                if (!target) {
                    throw { data: { message: _t("Choose a folder to link into.") } };
                }
                await this.orm.call(MODEL, "browser_link_add", [ids, target]);
            } else {
                await this.orm.call(MODEL, "browser_move", [ids, target]);
            }
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                (isLink ? _t("The link was rejected.") : _t("The move was rejected."));
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
    // Toolbar "New", and the tree pane's own per-folder "+" ▸ "New Article":
    // standard-layout create, no popup - a blank record is created right
    // under whatever's currently selected (or explicitly under parentId,
    // for the "+" menu; server-side create() defaults to the user's own
    // "My Documents" when neither is given) and opened immediately with
    // type_chosen=False, so the form's own DmsTypeChooser widget fills the
    // main pane asking what kind of document this should be, same idea as
    // Knowledge's empty-article "pick an option below" prompt - not a
    // separate dialog.
    async createBlankDocument(parentId) {
        const targetParentId = parentId !== undefined ? parentId : (this.state.selectedId || false);
        const newId = await this.orm.create(MODEL, [
            { name: _t("Untitled"), parent_id: targetParentId, type_chosen: false },
        ]);
        if (targetParentId) {
            this.expandedIds.add(targetParentId);
        }
        await this.refreshTree();
        this.openDocument(newId[0]);
    }

    // parentId lets a tree row's own "+" target that folder directly,
    // regardless of which folder is currently open in the flat pane -
    // defaults to the currently selected folder. This menu already asks
    // for a specific type up front, so the resulting record skips the
    // DmsTypeChooser prompt entirely (default_type_chosen: true) and lands
    // straight on the real editor for that type.
    newDocument(type, parentId, extraDefaults) {
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
                    default_type_chosen: true,
                    default_visibility_inherited: Boolean(targetParentId),
                    ...(extraDefaults || {}),
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

    // ---- cross-listing (multiple hierarchies) --------------------------
    // "Add to Another Folder..." Actions-menu item - the explicit
    // counterpart to Ctrl/Cmd+drag (onFolderDrop above). Both call the same
    // browser_link_add RPC, here across the whole current selection at once.
    bulkAddLink() {
        const ids = [...this.state.selection];
        const label = this.singleSelected ? this.singleSelected.name : _t("%s items", ids.length);
        this.dialog.add(SelectCreateDialog, {
            resModel: MODEL,
            title: _t("Add “%s” to Another Folder", label),
            domain: [["can_have_children", "=", true], ...(ids.length === 1 ? [["id", "!=", ids[0]]] : [])],
            multiSelect: false,
            noCreate: true,
            onSelected: async (resIds) => {
                if (!resIds?.length) {
                    return;
                }
                try {
                    await this.orm.call(MODEL, "browser_link_add", [ids, resIds[0]]);
                } catch (err) {
                    const msg =
                        (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        _t("Could not add this to that folder.");
                    this.notification.add(msg, { type: "danger" });
                    return;
                }
                this.notification.add(_t("Added to another folder."), { type: "info" });
                await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
            },
        });
    }

    // Jump to where a linked row's real parent_id lives - the tree/table
    // only ever show one thing at a time, so "go see the real one" is its
    // own action rather than something the current row can show inline.
    goToRealLocation(rec, ev) {
        ev?.stopPropagation();
        this.selectFolder(rec.real_parent_id || false);
    }

    // Removes every selected placement (browser_link_remove) - the
    // documents themselves, and any other folder they're filed in, are
    // untouched. No confirmation dialog: unlike Delete this is trivially
    // reversible (Add to Another Folder... puts it right back).
    async bulkRemoveLink() {
        const ids = [...this.state.selection];
        try {
            await this.orm.call(MODEL, "browser_link_remove", [ids, this.state.selectedId || false]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not remove this link.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        this.state.selection = new Set();
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    // ---- delete / trash -------------------------------------------------
    // "Delete" moves to Trash (reversible, no confirmation needed) unless
    // the row is already in_trash, in which case it's the real, permanent
    // unlink() - the only path that ever hard-deletes from the browser.
    deleteForeverBody(rec) {
        const hasRealChildren = rec.can_have_children && (rec.child_count || rec.has_children);
        const linkedCount = rec.linked_child_count || 0;
        if (hasRealChildren && linkedCount) {
            return _t(
                "Permanently delete “%(name)s” and everything inside it? " +
                    "%(linked)s linked document(s) filed in here will just be " +
                    "removed from this folder - they still exist at their real " +
                    "location. Everything else cannot be undone.",
                { name: rec.name, linked: linkedCount }
            );
        }
        if (linkedCount) {
            return _t(
                "Permanently delete “%(name)s”? %(linked)s linked document(s) " +
                    "filed in here will just be removed from this folder - they " +
                    "still exist at their real location.",
                { name: rec.name, linked: linkedCount }
            );
        }
        return hasRealChildren
            ? _t("Permanently delete “%s” and everything inside it? This cannot be undone.", rec.name)
            : _t("Permanently delete “%s”? This cannot be undone.", rec.name);
    }

    deleteRecord(rec, ev) {
        ev.stopPropagation();
        if (rec.in_trash) {
            this.deleteForeverRecord(rec);
        } else {
            this.trashRecord(rec);
        }
    }

    async trashRecord(rec) {
        try {
            await this.orm.call(MODEL, "browser_delete", [[rec.id]]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not delete this item.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        this.notification.add(_t("Moved “%s” to Trash.", rec.name), { type: "info" });
        if (this.state.selectedId === rec.id) {
            // Trashed the folder we're currently looking inside of - same
            // "no way to know where to go instead" reasoning as before,
            // root is always a safe fallback.
            this.selectFolder(false);
        }
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    deleteForeverRecord(rec) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete Forever"),
            body: this.deleteForeverBody(rec),
            confirmLabel: _t("Delete Forever"),
            confirmClass: "btn-danger",
            confirm: async () => {
                try {
                    await this.orm.call(MODEL, "browser_delete_forever", [[rec.id]]);
                } catch (err) {
                    const msg =
                        (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        _t("Could not permanently delete this item.");
                    this.notification.add(msg, { type: "danger" });
                    return;
                }
                if (this.state.selectedId === rec.id) {
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

    async restoreRecord(rec, ev) {
        ev.stopPropagation();
        try {
            await this.orm.call(MODEL, "browser_restore", [[rec.id]]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not restore this item.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        this.notification.add(_t("Restored “%s”.", rec.name), { type: "info" });
        await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
    }

    // Actions-menu Delete: bulkDelete only ever offers itself when
    // !anySelectedAreLinks (see the dropdown template), so every id here is
    // safe to trash/unlink outright - no per-row split needed the way a
    // mixed tree-delete would require. Permanent bulk delete only when
    // *every* selected row is already in Trash; otherwise it's a bulk trash.
    async bulkDelete() {
        const recs = this.selectedRecords;
        const ids = recs.map((r) => r.id);
        const allInTrash = recs.every((r) => r.in_trash);
        if (!allInTrash) {
            try {
                await this.orm.call(MODEL, "browser_delete", [ids]);
            } catch (err) {
                const msg =
                    (err && err.data && err.data.message) ||
                    (err && err.message) ||
                    _t("Could not delete these items.");
                this.notification.add(msg, { type: "danger" });
                return;
            }
            this.notification.add(_t("Moved %s items to Trash.", ids.length), { type: "info" });
            if (ids.includes(this.state.selectedId)) {
                this.selectFolder(false);
            }
            this.state.selection = new Set();
            await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
            return;
        }
        const anyWithChildren = recs.some(
            (r) => r.can_have_children && (r.child_count || r.has_children)
        );
        const body = recs.length === 1
            ? this.deleteForeverBody(recs[0])
            : anyWithChildren
                ? _t("Permanently delete %s items? Some contain other documents, " +
                    "which will be deleted too. This cannot be undone.", ids.length)
                : _t("Permanently delete %s items? This cannot be undone.", ids.length);
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete Forever"),
            body,
            confirmLabel: _t("Delete Forever"),
            confirmClass: "btn-danger",
            confirm: async () => {
                try {
                    await this.orm.call(MODEL, "browser_delete_forever", [ids]);
                } catch (err) {
                    const msg =
                        (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        _t("Could not permanently delete these items.");
                    this.notification.add(msg, { type: "danger" });
                    return;
                }
                if (ids.includes(this.state.selectedId)) {
                    this.selectFolder(false);
                }
                this.state.selection = new Set();
                await Promise.all([this.refreshTree(), this.loadContents(this.state.selectedId)]);
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

    // ---- Actions-menu bulk actions --------------------------------------
    async bulkPrint() {
        const action = await this.orm.call(MODEL, "action_report", [[...this.state.selection]]);
        this.action.doAction(action);
    }

    // Only ever offered when singleSelected is set (see the dropdown
    // template) - the download route and the publish toggle both only
    // make sense for one record at a time.
    bulkDownload() {
        window.open(`/sanare_dms/document/${this.singleSelected.id}/download`, "_blank");
    }

    async bulkTogglePublish() {
        const rec = this.singleSelected;
        try {
            rec.is_published = await this.orm.call(MODEL, "browser_toggle_publish", [[rec.id]]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not change publish status.");
            this.notification.add(msg, { type: "danger" });
        }
    }

    async bulkSetDisplayInPrint(value) {
        const ids = [...this.state.selection];
        await this.orm.write(MODEL, ids, { display_in_print: value });
        for (const rec of this.selectedRecords) {
            rec.display_in_print = value;
        }
    }

    async bulkSetTemplate(value) {
        const ids = [...this.state.selection];
        try {
            await this.orm.call(MODEL, "browser_set_template", [ids, value]);
        } catch (err) {
            const msg =
                (err && err.data && err.data.message) ||
                (err && err.message) ||
                _t("Could not change the template flag.");
            this.notification.add(msg, { type: "danger" });
            return;
        }
        for (const rec of this.selectedRecords) {
            rec.is_template = value;
        }
        this.loadTemplates();
    }

    iconFor(rec) {
        if (rec.is_folder) {
            return "fa-folder";
        }
        if (rec.content_type === "onlyoffice") {
            return OFFICE_ICONS[(rec.file_extension || "").toLowerCase()] || "fa-file-o";
        }
        return {
            html: "fa-file-code-o",
            knowledge_html: "fa-book",
            markdown: "fa-file-text-o",
            odoo_view: "fa-bar-chart",
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
