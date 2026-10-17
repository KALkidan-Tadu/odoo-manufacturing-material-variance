# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare, float_is_zero, float_round


class MrpMaterialVariance(models.Model):
    """Material consumption variance analysis for manufacturing orders.

    One line per manufacturing order / component product. Quantities are derived
    from standard ``stock.move`` raw material lines (``mrp.production.move_raw_ids``)
    rather than copying BoM or move data. Lines are synchronized on demand when
    opening the analysis so they stay aligned with manufacturing data without
    overriding core MRP methods.
    """

    _name = 'mrp.material.variance'
    _description = 'Manufacturing Material Variance'
    _order = 'production_id, component_id'
    _rec_name = 'display_name'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='production_id.company_id',
        store=True,
        index=True,
    )
    product_id = fields.Many2one(
        related='production_id.product_id',
        string='Finished Product',
        store=True,
        index=True,
    )
    production_state = fields.Selection(
        related='production_id.state',
        string='MO Status',
        store=True,
        index=True,
    )
    component_id = fields.Many2one(
        'product.product',
        string='Component',
        required=True,
        ondelete='restrict',
        index=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        required=True,
        help='Common UoM used for planned/actual comparison (component default UoM).',
    )
    stock_move_ids = fields.Many2many(
        'stock.move',
        'mrp_material_variance_stock_move_rel',
        'variance_id',
        'move_id',
        string='Component Moves',
        help='Raw material stock moves aggregated into this variance line.',
    )

    planned_qty = fields.Float(
        string='Planned Quantity',
        digits='Product Unit of Measure',
        compute='_compute_variance_values',
        store=True,
    )
    actual_qty = fields.Float(
        string='Actual Quantity',
        digits='Product Unit of Measure',
        compute='_compute_variance_values',
        store=True,
    )
    variance_qty = fields.Float(
        string='Quantity Variance',
        digits='Product Unit of Measure',
        compute='_compute_variance_values',
        store=True,
        help='Actual Quantity − Planned Quantity',
    )
    variance_percent = fields.Float(
        string='Variance %',
        digits=(16, 2),
        compute='_compute_variance_values',
        store=True,
        help='(Variance / Planned Quantity) × 100. Zero when planned is zero and actual is zero.',
    )
    tolerance_percent = fields.Float(
        string='Tolerance %',
        digits=(16, 2),
        compute='_compute_variance_values',
        store=True,
    )
    classification = fields.Selection(
        [
            ('within', 'Within Tolerance'),
            ('over', 'Overconsumption'),
            ('under', 'Underconsumption'),
            ('undefined', 'Undefined'),
        ],
        string='Classification',
        compute='_compute_variance_values',
        store=True,
        index=True,
    )
    is_provisional = fields.Boolean(
        string='Provisional',
        compute='_compute_variance_values',
        store=True,
        help='True when the manufacturing order is not done; consumption may still change.',
    )
    has_consumption_data = fields.Boolean(
        string='Has Consumption Data',
        compute='_compute_variance_values',
        store=True,
    )
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('production_id', 'component_id')
    def _compute_display_name(self):
        for line in self:
            mo_name = line.production_id.display_name or ''
            comp_name = line.component_id.display_name or ''
            line.display_name = f'{mo_name} — {comp_name}' if mo_name or comp_name else ''

    @api.depends(
        'stock_move_ids',
        'stock_move_ids.product_uom_qty',
        'stock_move_ids.quantity',
        'stock_move_ids.state',
        'stock_move_ids.picked',
        'stock_move_ids.product_uom',
        'stock_move_ids.move_line_ids.quantity',
        'stock_move_ids.move_line_ids.picked',
        'product_uom_id',
        'production_id.state',
        'production_id.company_id.material_variance_tolerance',
        'company_id.material_variance_tolerance',
    )
    def _compute_variance_values(self):
        for line in self:
            uom = line.product_uom_id or line.component_id.uom_id
            planned = line._get_planned_quantity(line.stock_move_ids, uom)
            actual = line._get_actual_quantity(line.stock_move_ids, uom)
            variance = actual - planned
            tolerance = line.company_id.material_variance_tolerance if line.company_id else 5.0
            if tolerance is False or tolerance is None:
                tolerance = 5.0

            rounding = uom.rounding if uom else 0.01
            planned = float_round(planned, precision_rounding=rounding)
            actual = float_round(actual, precision_rounding=rounding)
            variance = float_round(variance, precision_rounding=rounding)

            if float_is_zero(planned, precision_rounding=rounding):
                if float_is_zero(actual, precision_rounding=rounding):
                    variance_percent = 0.0
                    classification = 'within'
                else:
                    # Explicit zero-planned handling: any consumption is over.
                    variance_percent = 100.0
                    classification = 'over'
            else:
                variance_percent = (variance / planned) * 100.0
                variance_percent = float_round(variance_percent, precision_digits=2)
                classification = line._classify_variance(variance_percent, tolerance)

            line.planned_qty = planned
            line.actual_qty = actual
            line.variance_qty = variance
            line.variance_percent = variance_percent
            line.tolerance_percent = tolerance
            line.classification = classification
            line.is_provisional = line.production_id.state != 'done'
            line.has_consumption_data = any(
                move.state == 'done' or move.picked
                for move in line.stock_move_ids
                if move.state != 'cancel'
            )

    @api.model
    def _classify_variance(self, variance_percent, tolerance):
        """Classify using inclusive tolerance boundaries (|%| <= tolerance)."""
        if float_compare(tolerance, 0.0, precision_digits=4) < 0:
            tolerance = 0.0
        if float_compare(abs(variance_percent), tolerance, precision_digits=2) <= 0:
            return 'within'
        if float_compare(variance_percent, tolerance, precision_digits=2) > 0:
            return 'over'
        return 'under'

    @api.model
    def _get_planned_quantity(self, moves, target_uom):
        """Expected component quantity from MO raw moves (To Consume).

        Includes cancelled moves so components that were planned but never
        consumed still contribute to the planned baseline (product_uom_qty is
        retained on cancelled raw moves in standard MRP).
        """
        total = 0.0
        for move in moves:
            if not target_uom:
                total += move.product_uom_qty
                continue
            total += move.product_uom._compute_quantity(
                move.product_uom_qty, target_uom, rounding_method='HALF-UP',
            )
        return total

    @api.model
    def _get_actual_quantity(self, moves, target_uom):
        """Quantity actually consumed (picked / done), not merely reserved.

        Cancelled moves are excluded. Reserved but not picked quantities are
        ignored so availability is not treated as consumption.
        """
        total = 0.0
        for move in moves:
            if move.state == 'cancel':
                continue
            if move.state != 'done' and not move.picked:
                continue
            qty = move._get_picked_quantity()
            if not target_uom:
                total += qty
                continue
            total += move.product_uom._compute_quantity(
                qty, target_uom, rounding_method='HALF-UP',
            )
        return total

    @api.model
    def _eligible_production_domain(self):
        """MO states that may be analyzed (exclude draft and cancelled)."""
        return [('state', 'in', ('confirmed', 'progress', 'to_close', 'done'))]

    @api.model
    def _sync_for_productions(self, productions):
        """Create/update/delete variance lines for the given manufacturing orders."""
        productions = productions.filtered_domain(self._eligible_production_domain())
        if not productions:
            return self.browse()

        Variance = self.sudo()
        existing = Variance.search([('production_id', 'in', productions.ids)])
        existing_map = {
            (line.production_id.id, line.component_id.id): line
            for line in existing
        }
        seen = set()
        vals_to_create = []

        # Prefetch raw moves for all productions in one go.
        productions.mapped('move_raw_ids')

        for production in productions:
            moves_by_component = defaultdict(lambda: self.env['stock.move'])
            for move in production.move_raw_ids:
                if move.scrapped:
                    continue
                moves_by_component[move.product_id] |= move

            for component, moves in moves_by_component.items():
                key = (production.id, component.id)
                seen.add(key)
                uom = component.uom_id
                line_vals = {
                    'production_id': production.id,
                    'component_id': component.id,
                    'product_uom_id': uom.id,
                    'stock_move_ids': [(6, 0, moves.ids)],
                }
                existing_line = existing_map.get(key)
                if existing_line:
                    existing_line.write(line_vals)
                else:
                    vals_to_create.append(line_vals)

        stale = existing.filtered(
            lambda line: (line.production_id.id, line.component_id.id) not in seen
        )
        if stale:
            stale.unlink()
        if vals_to_create:
            Variance.create(vals_to_create)

        return Variance.search([('production_id', 'in', productions.ids)])

    @api.model
    def action_open_variance_analysis(self, domain=None):
        """Synchronize eligible lines then open the variance list action."""
        productions = self.env['mrp.production'].search(self._eligible_production_domain())
        self._sync_for_productions(productions)
        action = self.env['ir.actions.act_window']._for_xml_id(
            'mrp_material_variance.action_mrp_material_variance'
        )
        if domain:
            action['domain'] = domain
        return action
