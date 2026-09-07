# Sanare Document Management (`sanare_dms`) — Specification

Status: **v1**, Odoo 19 Community.
Modules: `sanare_dms` (core) + `sanare_dms_onlyoffice` (ONLYOFFICE bridge).

---

## 1. Goals

A hierarchical document store inside Odoo where every node is a `sanare.document`.
A node is either a **folder** or a **document** of one content type:

| Content type | Stored in | Editor |
|---|---|---|
| `folder` | — | — (container only) |
| `onlyoffice` | `ir.attachment` (binary: docx/xlsx/pptx/odt/ods/odp/…) | ONLYOFFICE Document Server, in-place, true multi-user co-editing |
| `html` | `content_html` (`Html` field) | Odoo `html_editor` wysiwyg + raw-HTML code view |
| `markdown` | `content_markdown` (`Text`, raw) | `sanare_markdown` widget — Odoo ACE editor + live HTML preview |

Any document can also contain child documents ("nested documents"): `parent_id`
is self-referential and a document — not only a folder — may be a parent.

Delivered features: owners & 3-tier visibility (Private / Shared / Public),
per-document version history with restore, a configurable multi-step approval
workflow (shipped configured as single-approver), hierarchical categories, tags,
and public exposure of approved documents on the website.

Explicitly **out of scope for v1** (agreed): read/download audit log, retention
policies, e-signature, exclusive edit-locking for ONLYOFFICE (the Document
Server does the concurrency control), public ONLYOFFICE preview (public office
documents are download-only).

---

## 2. Data model

### 2.1 `sanare.document`

`_inherit = ['mail.thread', 'mail.activity.mixin', 'website.published.mixin']`,
`_parent_store = True`, `_order = "is_folder desc, name"`.

| Field | Type | Notes |
|---|---|---|
| `name` | Char | required, tracked |
| `active` | Boolean | archive flag |
| `parent_id` | M2o `sanare.document` | `ondelete="cascade"`, self-ref |
| `parent_path` | Char | `_parent_store` index |
| `child_ids` / `child_count` | O2m / Integer | |
| `complete_name` | Char | stored, recursive — `Grandparent / Parent / Name` |
| `content_type` | Selection | `folder` / `onlyoffice` / `html` / `markdown`; read-only after create |
| `is_folder` | Boolean | stored compute (`content_type == 'folder'`) |
| `owner_id` | M2o `res.users` | default current user, required, tracked |
| `visibility` | Selection | `private` / `shared` / `public`, default `private`, tracked |
| `visibility_inherited` | Boolean | default `True` — take effective visibility + shares from parent |
| `effective_visibility` | Selection | stored recursive compute; resolves inheritance |
| `category_id` | M2o `sanare.document.category` | hierarchical |
| `tag_ids` | M2m `sanare.document.tag` | |
| `state` | Selection | `draft` / `to_approve` / `approved` / `rejected` |
| `content_html` | Html | `sanitize=True`, for `html` |
| `content_markdown` | Text | raw markdown, for `markdown` |
| `content_markdown_html` | Html | non-stored compute — rendered preview / website / print |
| `attachment_id` | M2o `ir.attachment` | office binary; `res_model='sanare.document'`, `res_id=id` |
| `file_name`, `file_extension`, `file_size`, `mimetype` | | office metadata |
| `version_ids` / `version_count` | O2m / Integer | |
| `version_number` | Integer | current revision counter, `copy=False` |
| `approved_version_id` | M2o `sanare.document.version` | the revision the public/website sees |
| `access_ids` | O2m `sanare.document.access` | explicit shares |
| `allowed_user_ids` | M2m `res.users` | **stored compute** — drives the read record rule |
| `allowed_write_user_ids` | M2m `res.users` | **stored compute** — drives the write record rule |
| `approval_rule_id` | M2o `sanare.document.approval.rule` | stored compute (category → nearest ancestor folder → none) |
| `approval_request_id` | M2o `sanare.document.approval.request` | current request, `copy=False` |

Computes:

* `effective_visibility` = `parent.effective_visibility` when
  `visibility_inherited and parent_id` else `visibility`.
* `allowed_user_ids` = users resolved from this node's `access_ids`
  (partner → `user_ids`, group → `users`), unioned with
  `parent.allowed_user_ids` when `visibility_inherited`. `allowed_write_user_ids`
  is the same but only for access rows with `permission in (write, approve)`.
  Both `store=True, recursive=True`.

`write()` override: when `content_html` / `content_markdown` is in `vals` and
context flag `dms_skip_version` is absent, snapshot a new version afterwards.
Editing an `approved` document creates a new `draft` revision while
`approved_version_id` keeps pointing at the last approved snapshot (public site
unaffected until re-approval). Editing a `to_approve` document cancels the open
request and returns to `draft`.

`_compute_can_publish` (override): `can_publish` is `True` only when the user has
write access **and** `state == 'approved'` **and**
`effective_visibility == 'public'`. `write()` re-checks this before allowing
`is_published = True`.

### 2.2 `sanare.document.version`

Immutable snapshot + audit trail. `_order = "document_id, version_number desc"`.

| Field | Notes |
|---|---|
| `document_id` | M2o, `ondelete="cascade"` |
| `version_number` | Integer, required |
| `name` | compute — `v{n}` |
| `content_type` | related, stored |
| `attachment_id` | M2o `ir.attachment` — office snapshot (own copy, `res_model='sanare.document.version'`) |
| `content_html` / `content_markdown` | text snapshots |
| `checksum`, `file_size` | office snapshot metadata |
| `changelog` | Char — auto ("Edited in ONLYOFFICE", "Content edited", "Submitted for approval", …) |
| `author_id` | M2o `res.users` |
| `create_date` | builtin |
| `is_current` / `is_approved` | computes |

Actions: `action_restore()` — writes the snapshot content back onto the document
as a **new** version (history is never rewritten); `action_open()` — office:
opens the snapshot read-only in ONLYOFFICE; html/markdown: read-only dialog.

Snapshots are created via `sudo()` from `sanare.document._snapshot_version()`;
it no-ops when the content is byte-identical to the latest version.

### 2.3 `sanare.document.access`

One explicit share. `document_id` (required, cascade), `partner_id` (M2o
`res.partner`), `group_id` (M2o `res.groups`), `permission`
(`read` / `write` / `approve`, default `read`). Constraint: exactly one of
partner/group set. Editing `access_ids` recomputes the owner document's
`allowed_*_user_ids` and, recursively, every inheriting descendant.

### 2.4 `sanare.document.category`

Hierarchical (`_parent_store`). `name`, `parent_id`, `complete_name` (stored),
`approval_rule_id` (M2o), `color`, `active`, `document_count`.

### 2.5 `sanare.document.tag`

`name` (unique, required), `color`, `active`.

### 2.6 Approval

**`sanare.document.approval.rule`** — `name`, `active`, `category_ids`
(M2m — categories this rule governs, mirrored to
`category.approval_rule_id`), `folder_ids` (M2m `sanare.document` — folders whose
subtree this rule governs), `line_ids` (ordered steps).

**`sanare.document.approval.rule.line`** — `sequence`, `name`, `approver_type`
(`users` / `group`), `user_ids` (M2m), `group_id` (M2o), `approval_mode`
(`all` — every approver must sign / `any` — one is enough, default `all`).
Lines run **sequentially** by `sequence`; the mode governs concurrency
**within** a step. This models both sequential chains and parallel steps.

**`sanare.document.approval.request`** — `document_id`, `rule_id`,
`version_number` (the frozen revision under review), `state`
(`pending` / `approved` / `rejected` / `cancelled`), `submitted_by`,
`submitted_on`, `line_ids`.

**`sanare.document.approval.request.line`** — `sequence`, `rule_line_id`,
`name`, `approver_ids` (M2m), `approval_mode`, `status`
(`pending` / `approved` / `rejected`), `approver_done_ids` (M2m — who has
signed, for `all` mode), `decided_by`, `decided_on`, `comment`.

Rule resolution (`_compute_approval_rule_id`, stored): `category_id.approval_rule_id`
→ else the rule whose `folder_ids` contains the nearest ancestor in
`parent_path` → else none.

Lifecycle on `sanare.document`:

* `action_submit()` — validates content present, snapshots the revision,
  resolves the rule, creates the request + lines (no rule ⇒ one `any` step
  targeting **Document Managers**), sets `state = to_approve`, raises a
  `mail.activity` (Odoo "To Do") for the first step's approvers.
* `action_approve()` — the current user (an approver of the active step, or a
  Manager) signs. `any` ⇒ step done; `all` ⇒ done when every `approver_id` has
  signed. When the last step closes: request `approved`, document `approved`,
  `approved_version_id` set to the reviewed revision, activities cleared.
* `action_reject()` — small wizard captures a reason; request + document
  `rejected`, reason posted to chatter, activities cleared.
* `action_reset_to_draft()` — cancels the open request and its activities.

---

## 3. Security

Groups (category *Document Management*):

* **Document User** (`group_dms_user`, implied by `base.group_user`) — create and
  fully manage own documents; read Shared documents they're granted and all
  Public documents; write Shared documents granted `write`/`approve`.
* **Document Approver** (`group_dms_approver`) — may approve steps they are
  named on.
* **Document Manager** (`group_dms_manager`, implies User) — unrestricted;
  approves any step; maintains categories, tags and approval rules.

`ir.model.access`:

| Model | User | Manager |
|---|---|---|
| `sanare.document` | R W C U | R W C U |
| `sanare.document.version` | R | R W C U |
| `sanare.document.access` | R W C U | R W C U |
| `sanare.document.category` | R | R W C U |
| `sanare.document.tag` | R C | R W C U |
| `sanare.document.approval.rule` (+ line) | R | R W C U |
| `sanare.document.approval.request` (+ line) | R | R W C U |

Record rules (on `group_dms_user`; Manager gets a global `[(1,'=',1)]`):

* **read** `sanare.document`:
  `owner_id = user` **or** `create_uid = user` **or**
  `effective_visibility = 'public'` **or** `user in allowed_user_ids`.
* **write / create / unlink** `sanare.document`:
  `owner_id = user` **or** `user in allowed_write_user_ids`.
* `sanare.document.access` and `…version` rules mirror the parent document's
  read / write reachability.

Approval request/line rows are only ever written through `sudo()` in the
lifecycle methods, after the caller's approver rights are checked in Python.

Public website access is `sudo()` behind an explicit gate:
`is_published and state == 'approved' and effective_visibility == 'public'`.

---

## 4. ONLYOFFICE bridge (`sanare_dms_onlyoffice`)

Depends `sanare_dms`, `onlyoffice_odoo`.

* `sanare.document` (`_inherit`):
  * `_ensure_office_attachment()` — for a `content_type == 'onlyoffice'` document
    with no `attachment_id`, create one from
    `onlyoffice_odoo.utils.file_utils.get_default_file_template(lang, ext)`
    (blank docx/xlsx/pptx shipped by the connector), linked
    `res_model='sanare.document', res_id=self.id`.
  * `action_edit_onlyoffice()` — returns an `ir.actions.act_url` to
    `/onlyoffice/editor/<attachment_id>` (`target="new"`). The connector builds
    the editor config; permissions fall out of `ir.attachment.has_access()`,
    which routes through the `sanare.document` record rules. Concurrent editors
    share the connector's `key` (`id + checksum`) ⇒ real-time co-editing.
  * `action_save_office_version()` — manual snapshot button.
* `ir.attachment` (`_inherit`): after `write()` touching `raw`/`datas`/`db_datas`
  on an attachment that backs a `content_type == 'onlyoffice'` document, and
  when `dms_skip_version` is not in context, call `_snapshot_version(trigger=
  'onlyoffice')`. The connector's generic callback path writes exactly once per
  editing session (status `2` = "must save"), so this yields one version per
  co-editing session, not per keystroke.
* View: injects the **Edit in ONLYOFFICE** / **Save version** buttons and the
  file widget into the document form's *Content* area.

No connector routes are overridden.

---

## 5. Markdown editor (`sanare_markdown` field widget)

`static/src/markdown_field/` — OWL component registered as field widget
`sanare_markdown` (`supportedTypes: ["text"]`).

* Left pane: Odoo core `CodeEditor` (`@web/core/code_editor`) — the ACE editor,
  plain mode (Odoo 19's `CodeEditor.MODES` has no `markdown`), `readonly` bound
  to the field.
* Right pane: live HTML preview, refreshed on a 400 ms debounce via
  `orm.call("sanare.document", "render_markdown_text", [text])`, rendered with
  OWL `markup()`.
* A toolbar toggle switches Editor / Split / Preview.

Server rendering — `sanare.document._render_markdown(text)`:

* Uses the `markdown` PyPI package when importable
  (`fenced_code, tables, toc, nl2br, sane_lists`).
* Falls back to a bundled dependency-free renderer (`_basic_markdown`) covering
  headings, `---` rules, fenced & inline code, bold/italic, links & images,
  ordered/unordered lists, block-quotes, paragraphs and hard line breaks.
* Output always passed through `odoo.tools.html_sanitize`.

`content_markdown_html` uses the same renderer for the read-only display, the
QWeb print report and the public website page.

Install `pip install markdown` on the server for full CommonMark-ish fidelity;
the module installs and works without it.

---

## 6. Website & portal

Controller `sanare_dms/controllers/main.py`:

| Route | Auth | Purpose |
|---|---|---|
| `GET /documents`, `/documents/page/<int>` | public | Paged, searchable index of published public documents (filter by category) |
| `GET /documents/<model("sanare.document"):document>` | public | Render one document — `html` inline, `markdown` via `content_markdown_html`, `onlyoffice` ⇒ metadata card + Download button |
| `GET /documents/<…>/download` | public | Stream the approved office snapshot / html / markdown source |
| `GET /my/documents`, `/my/documents/<int>` | user | Portal list of documents the user owns or may read |

Every public handler re-checks the publish gate and then `sudo()`s. Office
documents serve the `approved_version_id` snapshot, never the working copy.
`_compute_website_url` ⇒ `/documents/<id>`; sitemap includes published public
documents.

---

## 7. Backend UX

* App menu **Documents**.
  * *Documents* — search view defaults to *Top level* (`parent_id = False`);
    filters *Folders*, *Documents*, *My Documents*, *Shared with me*,
    *Pending my approval*, *Published*; group by Parent / Category / Owner /
    State / Content type. Kanban + list + form.
  * *Categories*, *Tags*, *Approval Rules* (Manager).
* Form: state statusbar + `Submit` / `Approve` / `Reject` / `Reset to Draft`;
  stat buttons *Versions* and *Contents*; publish widget (visible once
  approved + public). Tabs: **Content** (widget by `content_type`), **Sharing**
  (`visibility`, `visibility_inherited`, `access_ids` editable list),
  **Versions**, **Approval**, **Contents** (folders).
* QWeb report **Document** — prints `html` / `markdown` bodies to PDF (bare
  layout, no company letterhead — matches the `eos_dashboard` report convention).

---

## 8. Files

```
sanare_dms/
  __manifest__.py                 depends: mail, html_editor, website, portal
  models/  dms_document.py  dms_version.py  dms_access.py  dms_category.py
           dms_tag.py  dms_approval.py  dms_markdown.py
  wizard/  dms_reject_wizard.py
  controllers/main.py
  security/  dms_groups.xml  dms_rules.xml  ir.model.access.csv
  data/  dms_data.xml            root folder, default approval rule
  views/  dms_document_views.xml  dms_category_views.xml  dms_tag_views.xml
          dms_approval_views.xml  dms_menus.xml
          dms_portal_templates.xml  dms_website_templates.xml
  report/  dms_report.xml
  static/src/markdown_field/{markdown_field.js,markdown_field.xml,markdown_field.scss}
  static/src/scss/dms.scss

sanare_dms_onlyoffice/
  __manifest__.py                 depends: sanare_dms, onlyoffice_odoo
  models/  sanare_document.py  ir_attachment.py
  views/  dms_document_views.xml
```

---

## 9. Deployment

Both modules are first-party, committed to `github.com/steveocal/sanare`
(`main`). CloudPepper auto-pulls into
`extra-addons/sanare.git-<hash>/`. Install:

```
systemctl stop odona-gxcgtpype1.cloudpepper.site.service
sudo -u odoo TMPDIR=/var/odoo/<dir>/tmp \
  venv/bin/python3 src/odoo-bin --config odoo.conf \
  -d gxcgtpype1.cloudpepper.site \
  -i sanare_dms,sanare_dms_onlyoffice --stop-after-init --no-http
systemctl start odona-gxcgtpype1.cloudpepper.site.service
```

`onlyoffice_odoo` is already installed and pointed at the live Document Server;
the bridge reuses its configuration (URL + JWT secret) unchanged.
Optional: `pip install markdown` in the site venv for richer Markdown rendering.
