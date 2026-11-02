import re

from odoo import api, fields, models

# Specialty -> regex matched (case-insensitive) against the hospital name.
# Name-based only: a general hospital with a strong cardiac unit will not be
# tagged unless its name says so. Romanised Thai: "Dek" = child.
NAME_RULES = {
    'Oncology': r'\b(cancer|oncology|radiotherapy|tumou?r)\b',
    'Ophthalmology': r'\beyes?\b|\bophthalm',
    'ENT': r'\bear,? nose\b|\bENT\b',
    'Cardiology': r'\b(heart|cardiac|cardio\w*)\b',
    'Orthopaedics & Spine': r'\b(orthop(a)?edic\w*|spine|joint|bone)\b',
    'Neurology': r'\b(neurolog\w*|nerve|brain)\b',
    'Psychiatry & Mental Health': r'\b(psychiatr\w*|mental|mind)\b|mindmed',
    'Dental': r'\bdental\b|\bdentist',
    'Paediatrics': r'\b(child|children|kids?|p(a)?ediatric\w*|dek)\b',
    'Obstetrics & Gynaecology': r'\b(mother|maternity|gyn(a)?ecolog\w*|women)\b',
    'Dermatology & Aesthetics': r'\b(dermatolog\w*|skin|cosmetic|aesthetic|beauty|plastic)\b',
    'Nephrology': r'\b(kidney|renal|nephrolog\w*)\b',
    'Geriatrics': r'\b(geriatric|elderly|aged care)\b',
    'Rehabilitation': r'\brehabilit\w*',
    'Thai Traditional Medicine': r'\btraditional\b',
    # not "lung": it is a common Thai place-name syllable (Kho Lung, Huai Lung)
    'Chest & Respiratory': r'\b(chest|respiratory|thoracic|pulmonary)\b',
    'Infectious Disease': r'\b(infectious|tropical)\b',
    'Occupational Medicine': r'\boccupational\b',
    'Surgery': r'(?<!cosmetic )\bsurg(ical|ery)\b',
}


class EosHospitalSpecialty(models.Model):
    _name = 'eos.hospital.specialty'
    _description = 'Hospital Specialty'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()
    active = fields.Boolean(default=True)
    hospital_ids = fields.Many2many(
        'res.partner', 'eos_hospital_specialty_rel', 'specialty_id', 'partner_id',
        string='Hospitals')

    _name_uniq = models.Constraint('unique(name)', 'This specialty already exists.')

    @api.model
    def _eos_tag_hospitals_from_name(self, hospitals=None):
        """Add specialty tags to hospitals whose name matches NAME_RULES.

        Only adds tags (never removes), so manual tagging is kept. Returns
        {specialty name: number of hospitals newly tagged}.
        """
        if hospitals is None:
            hospitals = self.env['res.partner'].with_context(active_test=False).search(
                [('is_hospital', '=', True)])
        result = {}
        for spec_name, pattern in NAME_RULES.items():
            spec = self.with_context(active_test=False).search([('name', '=', spec_name)], limit=1)
            if not spec:
                spec = self.create({'name': spec_name})
            rx = re.compile(pattern, re.IGNORECASE)
            matched = hospitals.filtered(
                lambda p: p.name and rx.search(p.name) and spec not in p.specialty_ids)
            if matched:
                matched.write({'specialty_ids': [(4, spec.id)]})
            result[spec_name] = len(matched)
        return result
