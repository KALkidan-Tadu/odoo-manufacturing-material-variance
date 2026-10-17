# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpMaterialVarianceDashboard(models.TransientModel):
    """Simple summary of material variance classifications.

    Uses standard form fields rather than a custom OWL dashboard. Values are
    recomputed whenever the wizard is opened after synchronizing analysis lines.
    """

    _name = 'mrp.material.variance.dashboard'
    _description = 'Material Variance Summary'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    mo_count = fields.Integer(string='Manufacturing Orders Analyzed', readonly=True)
    component_exceeding_count = fields.Integer(
        string='Components Exceeding Tolerance',
        readonly=True,
    )
    overconsumption_count = fields.Integer(string='Overconsumption Cases', readonly=True)
    underconsumption_count = fields.Integer(string='Underconsumption Cases', readonly=True)
    within_tolerance_count = fields.Integer(string='Within Tolerance', readonly=True)
    provisional_count = fields.Integer(string='Provisional Lines', readonly=True)
    tolerance_percent = fields.Float(
        string='Company Tolerance %',
        related='company_id.material_variance_tolerance',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        Variance = self.env['mrp.material.variance']
        productions = self.env['mrp.production'].search(
            Variance._eligible_production_domain() + [('company_id', '=', company.id)]
        )
        lines = Variance._sync_for_productions(productions)
        res.update(self._prepare_summary_values(lines, company))
        return res

    @api.model
    def _prepare_summary_values(self, lines, company):
        over = lines.filtered(lambda line: line.classification == 'over')
        under = lines.filtered(lambda line: line.classification == 'under')
        within = lines.filtered(lambda line: line.classification == 'within')
        return {
            'company_id': company.id,
            'mo_count': len(lines.mapped('production_id')),
            'component_exceeding_count': len(over) + len(under),
            'overconsumption_count': len(over),
            'underconsumption_count': len(under),
            'within_tolerance_count': len(within),
            'provisional_count': len(lines.filtered('is_provisional')),
        }

    def action_refresh(self):
        self.ensure_one()
        Variance = self.env['mrp.material.variance']
        productions = self.env['mrp.production'].search(
            Variance._eligible_production_domain() + [('company_id', '=', self.company_id.id)]
        )
        lines = Variance._sync_for_productions(productions)
        self.write(self._prepare_summary_values(lines, self.company_id))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_variances(self):
        self.ensure_one()
        return self.env['mrp.material.variance'].action_open_variance_analysis(
            domain=[('company_id', '=', self.company_id.id)]
        )
