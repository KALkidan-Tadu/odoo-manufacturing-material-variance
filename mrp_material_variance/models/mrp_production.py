# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    material_variance_line_ids = fields.One2many(
        'mrp.material.variance',
        'production_id',
        string='Material Variance Lines',
    )
    material_variance_count = fields.Integer(
        string='Material Variance Count',
        compute='_compute_material_variance_count',
    )

    @api.depends('material_variance_line_ids')
    def _compute_material_variance_count(self):
        grouped = self.env['mrp.material.variance']._read_group(
            [('production_id', 'in', self.ids)],
            ['production_id'],
            ['__count'],
        )
        counts = {production.id: count for production, count in grouped}
        for production in self:
            production.material_variance_count = counts.get(production.id, 0)

    def action_view_material_variance(self):
        self.ensure_one()
        self.env['mrp.material.variance']._sync_for_productions(self)
        action = self.env['ir.actions.act_window']._for_xml_id(
            'mrp_material_variance.action_mrp_material_variance'
        )
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {
            **self.env.context,
            'default_production_id': self.id,
            'search_default_production_id': self.id,
        }
        action['name'] = _('Material Variance: %s', self.name)
        return action
