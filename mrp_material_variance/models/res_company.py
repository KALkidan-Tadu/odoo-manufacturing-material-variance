# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.float_utils import float_compare


class ResCompany(models.Model):
    _inherit = 'res.company'

    material_variance_tolerance = fields.Float(
        string='Material Variance Tolerance (%)',
        default=5.0,
        help='Default acceptable absolute variance percentage for material '
             'consumption. Values within ± this percentage are classified as '
             'within tolerance. Extensible later for product-specific limits.',
    )

    @api.constrains('material_variance_tolerance')
    def _check_material_variance_tolerance(self):
        for company in self:
            if float_compare(company.material_variance_tolerance, 0.0, precision_digits=4) < 0:
                raise ValidationError(_(
                    'Material variance tolerance cannot be negative.'
                ))

    def write(self, vals):
        vals = dict(vals)
        if 'material_variance_tolerance' in vals and not self.env.su:
            if not self.env.user.has_group('mrp.group_mrp_manager'):
                raise AccessError(_(
                    'Only Manufacturing Administrators can modify the material '
                    'variance tolerance.'
                ))
            # Managers may not have full res.company write rights (Settings ACL).
            # Allow updating this single business setting without exposing other
            # company fields.
            tolerance = vals.pop('material_variance_tolerance')
            super(ResCompany, self.sudo()).write({
                'material_variance_tolerance': tolerance,
            })
            if not vals:
                return True
        return super().write(vals)
