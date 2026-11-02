from odoo import api, fields, models

# Odoo ships Thai provinces with Thai-script names only (base/data/
# res.country.state.csv) and the field is not translatable, so there is no
# English translation to load. English names keyed on the ISO 3166-2 code.
TH_PROVINCES_EN = {
    'TH-10': 'Bangkok', 'TH-11': 'Samut Prakan', 'TH-12': 'Nonthaburi',
    'TH-13': 'Pathum Thani', 'TH-14': 'Phra Nakhon Si Ayutthaya',
    'TH-15': 'Ang Thong', 'TH-16': 'Lopburi', 'TH-17': 'Sing Buri',
    'TH-18': 'Chai Nat', 'TH-19': 'Saraburi', 'TH-20': 'Chonburi',
    'TH-21': 'Rayong', 'TH-22': 'Chanthaburi', 'TH-23': 'Trat',
    'TH-24': 'Chachoengsao', 'TH-25': 'Prachinburi', 'TH-26': 'Nakhon Nayok',
    'TH-27': 'Sa Kaeo', 'TH-30': 'Nakhon Ratchasima', 'TH-31': 'Buriram',
    'TH-32': 'Surin', 'TH-33': 'Sisaket', 'TH-34': 'Ubon Ratchathani',
    'TH-35': 'Yasothon', 'TH-36': 'Chaiyaphum', 'TH-37': 'Amnat Charoen',
    'TH-38': 'Bueng Kan', 'TH-39': 'Nong Bua Lamphu', 'TH-40': 'Khon Kaen',
    'TH-41': 'Udon Thani', 'TH-42': 'Loei', 'TH-43': 'Nong Khai',
    'TH-44': 'Maha Sarakham', 'TH-45': 'Roi Et', 'TH-46': 'Kalasin',
    'TH-47': 'Sakon Nakhon', 'TH-48': 'Nakhon Phanom', 'TH-49': 'Mukdahan',
    'TH-50': 'Chiang Mai', 'TH-51': 'Lamphun', 'TH-52': 'Lampang',
    'TH-53': 'Uttaradit', 'TH-54': 'Phrae', 'TH-55': 'Nan', 'TH-56': 'Phayao',
    'TH-57': 'Chiang Rai', 'TH-58': 'Mae Hong Son', 'TH-60': 'Nakhon Sawan',
    'TH-61': 'Uthai Thani', 'TH-62': 'Kamphaeng Phet', 'TH-63': 'Tak',
    'TH-64': 'Sukhothai', 'TH-65': 'Phitsanulok', 'TH-66': 'Phichit',
    'TH-67': 'Phetchabun', 'TH-70': 'Ratchaburi', 'TH-71': 'Kanchanaburi',
    'TH-72': 'Suphan Buri', 'TH-73': 'Nakhon Pathom', 'TH-74': 'Samut Sakhon',
    'TH-75': 'Samut Songkhram', 'TH-76': 'Phetchaburi',
    'TH-77': 'Prachuap Khiri Khan', 'TH-80': 'Nakhon Si Thammarat',
    'TH-81': 'Krabi', 'TH-82': 'Phang Nga', 'TH-83': 'Phuket',
    'TH-84': 'Surat Thani', 'TH-85': 'Ranong', 'TH-86': 'Chumphon',
    'TH-90': 'Songkhla', 'TH-91': 'Satun', 'TH-92': 'Trang',
    'TH-93': 'Phatthalung', 'TH-94': 'Pattani', 'TH-95': 'Yala',
    'TH-96': 'Narathiwat',
}


class ResCountryState(models.Model):
    _inherit = 'res.country.state'
    _rec_names_search = ['name', 'code', 'name_en']

    name_en = fields.Char(
        string='English Name',
        help='Shown instead of the local-script name wherever the state / '
             'province is displayed. Postal addresses still use the name.')

    @api.depends('name_en')
    def _compute_display_name(self):
        super()._compute_display_name()
        for state in self.filtered('name_en'):
            if self.env.context.get('formatted_display_name'):
                state.display_name = f"{state.name_en} \t --{state.country_id.code}--"
            else:
                state.display_name = f"{state.name_en} ({state.country_id.code})"

    @api.model
    def _eos_load_english_names(self):
        """Fill English names for Thai provinces (run on install/upgrade)."""
        thailand = self.env.ref('base.th', raise_if_not_found=False)
        if not thailand:
            return
        for state in self.search([('country_id', '=', thailand.id)]):
            name_en = TH_PROVINCES_EN.get(state.code)
            if name_en and not state.name_en:
                state.name_en = name_en
