/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { Component, useState, useChildSubEnv, useEffect, useRef, onMounted } from "@odoo/owl";

const MODEL = "sanare.document";
const NEW_TYPES = [
    ["folder", _t("Folder")],
    ["html", _t("Web Page (HTML)")],
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
}
DmsTreeNode.components = { DmsTreeNode };

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
        this.newTypes = NEW_TYPES;

        this.expandedIds = new Set();
        this.dragIds = [];

        this.state = useState({
            tree: [],
            selectedId: false, // false === the "Documents" root
            breadcrumb: [],
            records: [],
            selection: new Set(),
            loadingTree: true,
            loadingList: true,
            dragOverId: null,
            creatingFolder: false,
            newFolderName: "",
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
                toggle: (n) => this.toggleNode(n),
                select: (id) => this.selectFolder(id),
                dragStart: (node, ev) =>
                    this.onItemDragStart({ id: node.id, is_folder: true }, ev),
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
        });
    }

    // ---- data --------------------------------------------------------
    async buildBranch(parentId) {
        const raw = await this.orm.call(MODEL, "browser_folders", [parentId || false]);
        const nodes = [];
        for (const f of raw) {
            const expanded = this.expandedIds.has(f.id);
            nodes.push({
                ...f,
                expanded,
                loading: false,
                children:
                    expanded && f.has_subfolders ? await this.buildBranch(f.id) : null,
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
        } catch (err) {
            this.state.breadcrumb = [];
            this.state.records = [];
            this.notification.add(_t("Could not load this folder."), { type: "danger" });
        } finally {
            this.state.loadingList = false;
        }
    }

    async toggleNode(node) {
        if (node.expanded) {
            node.expanded = false;
            this.expandedIds.delete(node.id);
            return;
        }
        node.expanded = true;
        this.expandedIds.add(node.id);
        if (node.children === null && node.has_subfolders) {
            node.loading = true;
            node.children = await this.buildBranch(node.id);
            node.loading = false;
        }
    }

    selectFolder(folderId) {
        this.loadContents(folderId || false);
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

    newDocument(type) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: MODEL,
                views: [[false, "form"]],
                target: "current",
                context: {
                    default_parent_id: this.state.selectedId || false,
                    default_content_type: type,
                    default_visibility_inherited: Boolean(this.state.selectedId),
                },
            },
            { onClose: () => this.loadContents(this.state.selectedId) }
        );
    }

    iconFor(rec) {
        if (rec.is_folder) {
            return "fa-folder";
        }
        return {
            onlyoffice: "fa-file-word-o",
            html: "fa-file-code-o",
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
