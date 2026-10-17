# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    material_variance_tolerance = fields.Float(
        related='company_id.material_variance_tolerance',
        string='Material Variance Tolerance (%)',
        readonly=False,
    )
