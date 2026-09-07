from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SanareDocumentApprovalRule(models.Model):
    _name = "sanare.document.approval.rule"
    _description = "Document Approval Rule"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    category_ids = fields.One2many(
        "sanare.document.category",
        "approval_rule_id",
        string="Categories",
        help="Documents in these categories use this rule.",
    )
    folder_ids = fields.Many2many(
        "sanare.document",
        "sanare_dms_rule_folder_rel",
        "rule_id",
        "document_id",
        string="Folders",
        domain=[("content_type", "=", "folder")],
        help="Documents anywhere under these folders use this rule "
        "(unless their category names another rule).",
    )
    line_ids = fields.One2many(
        "sanare.document.approval.rule.line", "rule_id", string="Approval Steps", copy=True
    )
    note = fields.Text()

    def name_get_steps(self):
        self.ensure_one()
        return len(self.line_ids)


class SanareDocumentApprovalRuleLine(models.Model):
    _name = "sanare.document.approval.rule.line"
    _description = "Document Approval Step"
    _order = "rule_id, sequence, id"

    rule_id = fields.Many2one(
        "sanare.document.approval.rule", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Step", required=True, default="Approval")
    approver_type = fields.Selection(
        [("users", "Specific Users"), ("group", "Anyone in a Group")],
        default="users",
        required=True,
    )
    user_ids = fields.Many2many("res.users", string="Approvers")
    group_id = fields.Many2one("res.groups", string="Approver Group")
    approval_mode = fields.Selection(
        [("all", "All must approve"), ("any", "Any one may approve")],
        default="all",
        required=True,
    )

    @api.constrains("approver_type", "user_ids", "group_id")
    def _check_approvers(self):
        for line in self:
            if line.approver_type == "users" and not line.user_ids:
                raise ValidationError(self.env._("Step '%s' has no approvers.", line.name))
            if line.approver_type == "group" and not line.group_id:
                raise ValidationError(self.env._("Step '%s' has no approver group.", line.name))

    def _resolve_approvers(self):
        self.ensure_one()
        if self.approver_type == "group":
            return self.group_id.all_user_ids
        return self.user_ids


class SanareDocumentApprovalRequest(models.Model):
    _name = "sanare.document.approval.request"
    _description = "Document Approval Request"
    _order = "id desc"

    document_id = fields.Many2one(
        "sanare.document", required=True, ondelete="cascade", index=True
    )
    rule_id = fields.Many2one("sanare.document.approval.rule")
    version_number = fields.Integer(string="Revision")
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        required=True,
    )
    submitted_by = fields.Many2one("res.users", default=lambda s: s.env.user)
    submitted_on = fields.Datetime(default=fields.Datetime.now)
    line_ids = fields.One2many(
        "sanare.document.approval.request.line", "request_id", string="Steps"
    )
    reject_reason = fields.Text()

    def _build_lines(self):
        """Materialise request steps from the rule (or a Manager fallback step)."""
        self.ensure_one()
        Line = self.env["sanare.document.approval.request.line"]
        self.line_ids.unlink()
        if self.rule_id and self.rule_id.line_ids:
            for rline in self.rule_id.line_ids.sorted(lambda l: (l.sequence, l.id)):
                Line.create(
                    {
                        "request_id": self.id,
                        "sequence": rline.sequence,
                        "name": rline.name,
                        "rule_line_id": rline.id,
                        "approval_mode": rline.approval_mode,
                        "approver_ids": [(6, 0, rline._resolve_approvers().ids)],
                    }
                )
        else:
            managers = self.env.ref("sanare_dms.group_dms_manager").all_user_ids
            Line.create(
                {
                    "request_id": self.id,
                    "sequence": 10,
                    "name": self.env._("Manager approval"),
                    "approval_mode": "any",
                    "approver_ids": [(6, 0, managers.ids)],
                }
            )

    def _current_line(self):
        self.ensure_one()
        return self.line_ids.sorted(lambda l: (l.sequence, l.id)).filtered(
            lambda l: l.status == "pending"
        )[:1]

    def _activate_next_step(self):
        self.ensure_one()
        line = self._current_line()
        if not line:
            return False
        self.document_id._schedule_approval_activities(line._pending_approvers())
        return line


class SanareDocumentApprovalRequestLine(models.Model):
    _name = "sanare.document.approval.request.line"
    _description = "Document Approval Request Step"
    _order = "request_id, sequence, id"

    request_id = fields.Many2one(
        "sanare.document.approval.request", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Step")
    rule_line_id = fields.Many2one("sanare.document.approval.rule.line")
    approver_ids = fields.Many2many("res.users", string="Approvers")
    approval_mode = fields.Selection(
        [("all", "All must approve"), ("any", "Any one may approve")],
        default="all",
        required=True,
    )
    approver_done_ids = fields.Many2many(
        "res.users", "sanare_dms_reqline_done_rel", string="Signed off by"
    )
    status = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="pending",
        required=True,
    )
    decided_by = fields.Many2one("res.users")
    decided_on = fields.Datetime()
    comment = fields.Char()

    def _is_approver(self, user):
        self.ensure_one()
        return user in self.approver_ids

    def _pending_approvers(self):
        self.ensure_one()
        return self.approver_ids - self.approver_done_ids

    def _register_decision(self, user, decision, comment=False):
        """decision in ('approved', 'rejected'). Returns True when the step closes."""
        self.ensure_one()
        self.decided_by = user.id
        self.decided_on = fields.Datetime.now()
        if comment:
            self.comment = comment
        if decision == "rejected":
            self.status = "rejected"
            return True
        self.approver_done_ids = [(4, user.id)]
        if self.approval_mode == "any" or not self._pending_approvers():
            self.status = "approved"
            return True
        return False
