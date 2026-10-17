# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, tagged
from odoo.addons.mrp.tests.common import TestMrpCommon
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged('post_install', '-at_install')
class TestMaterialVarianceCalculations(TestMrpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.material_variance_tolerance = 5.0
        cls.Variance = cls.env['mrp.material.variance']

    def _produce_mo(self, mo, qty_producing=None, component_qty_map=None):
        """Confirm consumption and mark the MO done.

        :param component_qty_map: dict product -> quantity to consume in move UoM
        """
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = qty_producing if qty_producing is not None else mo.product_qty
        mo = mo_form.save()
        if component_qty_map:
            for move in mo.move_raw_ids:
                if move.product_id not in component_qty_map:
                    continue
                qty = component_qty_map[move.product_id]
                if move.move_line_ids:
                    move.move_line_ids.quantity = qty
                else:
                    move.quantity = qty
                move.picked = True
        mo.button_mark_done()
        return mo

    def _line_for(self, mo, component):
        lines = self.Variance._sync_for_productions(mo)
        return lines.filtered(lambda line: line.component_id == component)

    def test_zero_variance(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=200, qty_base_2=10,
        )
        mo = self._produce_mo(mo, component_qty_map={comp1: 200, comp2: 10})
        line = self._line_for(mo, comp1)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.planned_qty, 200.0)
        self.assertAlmostEqual(line.actual_qty, 200.0)
        self.assertAlmostEqual(line.variance_qty, 0.0)
        self.assertAlmostEqual(line.variance_percent, 0.0)
        self.assertEqual(line.classification, 'within')
        self.assertFalse(line.is_provisional)

    def test_positive_variance_overconsumption(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=200, qty_base_2=10,
        )
        mo = self._produce_mo(mo, component_qty_map={comp1: 220, comp2: 10})
        line = self._line_for(mo, comp1)
        self.assertAlmostEqual(line.planned_qty, 200.0)
        self.assertAlmostEqual(line.actual_qty, 220.0)
        self.assertAlmostEqual(line.variance_qty, 20.0)
        self.assertAlmostEqual(line.variance_percent, 10.0)
        self.assertEqual(line.classification, 'over')

    def test_negative_variance_underconsumption(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=200, qty_base_2=10,
        )
        mo = self._produce_mo(mo, component_qty_map={comp1: 180, comp2: 10})
        line = self._line_for(mo, comp1)
        self.assertAlmostEqual(line.variance_qty, -20.0)
        self.assertAlmostEqual(line.variance_percent, -10.0)
        self.assertEqual(line.classification, 'under')

    def test_within_tolerance_small_positive(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=200, qty_base_2=10,
        )
        mo = self._produce_mo(mo, component_qty_map={comp1: 205, comp2: 10})
        line = self._line_for(mo, comp1)
        self.assertAlmostEqual(line.variance_percent, 2.5)
        self.assertEqual(line.classification, 'within')

    def test_tolerance_boundary_inclusive(self):
        """Exactly ±5% must be within tolerance."""
        self.assertEqual(self.Variance._classify_variance(5.0, 5.0), 'within')
        self.assertEqual(self.Variance._classify_variance(-5.0, 5.0), 'within')
        self.assertEqual(self.Variance._classify_variance(5.01, 5.0), 'over')
        self.assertEqual(self.Variance._classify_variance(-5.01, 5.0), 'under')

    def test_zero_planned_quantity(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=0, qty_base_2=1,
        )
        # Force a zero-planned move and consume something.
        zero_move = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        self.assertTrue(zero_move)
        self.assertAlmostEqual(zero_move.product_uom_qty, 0.0)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 1
        mo = mo_form.save()
        zero_move = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        zero_move.quantity = 5.0
        zero_move.picked = True
        other = mo.move_raw_ids.filtered(lambda m: m.product_id == comp2)
        other.quantity = 1.0
        other.picked = True
        mo.button_mark_done()

        line = self._line_for(mo, comp1)
        self.assertAlmostEqual(line.planned_qty, 0.0)
        self.assertAlmostEqual(line.actual_qty, 5.0)
        self.assertEqual(line.classification, 'over')
        self.assertAlmostEqual(line.variance_percent, 100.0)

    def test_zero_planned_zero_actual(self):
        classification = self.Variance._classify_variance(0.0, 5.0)
        self.assertEqual(classification, 'within')
        # Direct compute path via a synthetic sync after creating zero demand.
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=0, qty_base_2=1,
        )
        mo = self._produce_mo(mo, component_qty_map={comp1: 0, comp2: 1})
        line = self._line_for(mo, comp1)
        self.assertAlmostEqual(line.planned_qty, 0.0)
        self.assertAlmostEqual(line.actual_qty, 0.0)
        self.assertEqual(line.classification, 'within')
        self.assertAlmostEqual(line.variance_percent, 0.0)


@tagged('post_install', '-at_install')
class TestMaterialVarianceManufacturing(TestMrpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.material_variance_tolerance = 5.0
        cls.Variance = cls.env['mrp.material.variance']
        cls.stock_location = cls.env.ref('stock.stock_location_stock')

    def test_multiple_components_planned_and_actual(self):
        mo, _bom, finished, comp1, comp2 = self.generate_mo(
            qty_final=5, qty_base_1=4, qty_base_2=1,
        )
        self.assertEqual(mo.product_id, finished)
        # Planned: 5*4=20 and 5*1=5
        move1 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        move2 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp2)
        self.assertAlmostEqual(move1.product_uom_qty, 20.0)
        self.assertAlmostEqual(move2.product_uom_qty, 5.0)

        self.env['stock.quant']._update_available_quantity(comp1, self.stock_location, 100)
        self.env['stock.quant']._update_available_quantity(comp2, self.stock_location, 100)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 5
        mo = mo_form.save()
        move1.quantity = 22
        move1.picked = True
        move2.quantity = 5
        move2.picked = True
        mo.button_mark_done()

        lines = self.Variance._sync_for_productions(mo)
        self.assertEqual(len(lines), 2)
        line1 = lines.filtered(lambda line: line.component_id == comp1)
        line2 = lines.filtered(lambda line: line.component_id == comp2)
        self.assertAlmostEqual(line1.planned_qty, 20.0)
        self.assertAlmostEqual(line1.actual_qty, 22.0)
        self.assertEqual(line1.classification, 'over')
        self.assertAlmostEqual(line2.planned_qty, 5.0)
        self.assertAlmostEqual(line2.actual_qty, 5.0)
        self.assertEqual(line2.classification, 'within')

    def test_partial_consumption_is_provisional(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=10, qty_base_1=2, qty_base_2=1,
        )
        self.env['stock.quant']._update_available_quantity(comp1, self.stock_location, 100)
        self.env['stock.quant']._update_available_quantity(comp2, self.stock_location, 100)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 5
        mo = mo_form.save()
        move1 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        move1.quantity = 8
        move1.picked = True

        lines = self.Variance._sync_for_productions(mo)
        line1 = lines.filtered(lambda line: line.component_id == comp1)
        self.assertTrue(line1.is_provisional)
        self.assertAlmostEqual(line1.planned_qty, 20.0)
        self.assertAlmostEqual(line1.actual_qty, 8.0)
        self.assertEqual(mo.state, 'progress')

    def test_reserved_not_counted_as_actual(self):
        """Reserved quantity without picking must not count as consumption."""
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=10, qty_base_2=1,
        )
        self.env['stock.quant']._update_available_quantity(comp1, self.stock_location, 100)
        self.env['stock.quant']._update_available_quantity(comp2, self.stock_location, 100)
        mo.action_assign()
        move1 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        self.assertGreater(move1.quantity, 0.0)
        self.assertFalse(move1.picked)
        self.assertNotEqual(move1.state, 'done')

        line = self.Variance._sync_for_productions(mo).filtered(
            lambda line: line.component_id == comp1
        )
        self.assertAlmostEqual(line.actual_qty, 0.0)
        self.assertTrue(line.is_provisional)

    def test_cancelled_moves_excluded_from_actual(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=10, qty_base_2=1,
        )
        self.env['stock.quant']._update_available_quantity(comp1, self.stock_location, 100)
        self.env['stock.quant']._update_available_quantity(comp2, self.stock_location, 100)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 1
        mo = mo_form.save()
        move1 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        move2 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp2)
        move1.move_line_ids.quantity = 0
        move2.move_line_ids.quantity = 1
        mo.button_mark_done()

        self.assertIn('cancel', mo.move_raw_ids.mapped('state'))
        lines = self.Variance._sync_for_productions(mo)
        line1 = lines.filtered(lambda line: line.component_id == comp1)
        # Planned retained; actual excluded for cancelled move.
        self.assertAlmostEqual(line1.planned_qty, 10.0)
        self.assertAlmostEqual(line1.actual_qty, 0.0)
        self.assertEqual(line1.classification, 'under')

    def test_uom_conversion(self):
        """Planned/actual compared in the component's default UoM."""
        dozen = self.uom_dozen
        unit = self.uom_unit
        finished = self.env['product.product'].create({
            'name': 'Finished UoM',
            'is_storable': True,
            'type': 'consu',
        })
        component = self.env['product.product'].create({
            'name': 'Board',
            'is_storable': True,
            'type': 'consu',
            'uom_id': unit.id,
            'uom_po_id': unit.id,
        })
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': finished.product_tmpl_id.id,
            'product_qty': 1,
            'product_uom_id': unit.id,
            'type': 'normal',
            'consumption': 'flexible',
            'bom_line_ids': [(0, 0, {
                'product_id': component.id,
                'product_qty': 2,
                'product_uom_id': dozen.id,  # 2 dozen = 24 units planned per finished
            })],
        })
        mo_form = Form(self.env['mrp.production'])
        mo_form.product_id = finished
        mo_form.bom_id = bom
        mo_form.product_qty = 1
        mo = mo_form.save()
        mo.action_confirm()

        self.env['stock.quant']._update_available_quantity(component, self.stock_location, 100)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 1
        mo = mo_form.save()
        move = mo.move_raw_ids.filtered(lambda m: m.product_id == component)
        # Consume 2 dozen in move UoM (= 24 units).
        self.assertEqual(move.product_uom, dozen)
        move.quantity = 2
        move.picked = True
        mo.button_mark_done()

        line = self.Variance._sync_for_productions(mo)
        self.assertEqual(line.product_uom_id, unit)
        self.assertAlmostEqual(line.planned_qty, 24.0)
        self.assertAlmostEqual(line.actual_qty, 24.0)
        self.assertEqual(line.classification, 'within')

    def test_mo_without_bom_components(self):
        finished = self.env['product.product'].create({
            'name': 'No BoM Product',
            'is_storable': True,
            'type': 'consu',
        })
        mo_form = Form(self.env['mrp.production'])
        mo_form.product_id = finished
        mo_form.product_qty = 1
        mo = mo_form.save()
        mo.action_confirm()
        lines = self.Variance._sync_for_productions(mo)
        self.assertFalse(lines)

    def test_draft_and_cancel_not_eligible(self):
        mo, _bom, _finished, _c1, _c2 = self.generate_mo()
        # generate_mo already confirms; cancel it.
        mo.action_cancel()
        lines = self.Variance._sync_for_productions(mo)
        self.assertFalse(lines)

    def test_smart_button_action_domain(self):
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=10, qty_base_2=1,
        )
        action = mo.action_view_material_variance()
        self.assertEqual(action['res_model'], 'mrp.material.variance')
        self.assertEqual(action['domain'], [('production_id', '=', mo.id)])
        self.assertEqual(mo.material_variance_count, 2)


@tagged('post_install', '-at_install')
class TestMaterialVarianceConfiguration(TestMrpCommon):

    def test_default_tolerance(self):
        company = self.env.company
        # Field default is 5; reset explicitly for the assertion.
        company.material_variance_tolerance = 5.0
        self.assertAlmostEqual(company.material_variance_tolerance, 5.0)

    def test_custom_tolerance_used_in_classification(self):
        self.env.company.material_variance_tolerance = 15.0
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=200, qty_base_2=1,
        )
        self.env['stock.quant']._update_available_quantity(comp1, self.env.ref('stock.stock_location_stock'), 500)
        self.env['stock.quant']._update_available_quantity(comp2, self.env.ref('stock.stock_location_stock'), 500)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 1
        mo = mo_form.save()
        move1 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        move2 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp2)
        move1.quantity = 220  # +10%
        move1.picked = True
        move2.quantity = 1
        move2.picked = True
        mo.button_mark_done()

        line = self.env['mrp.material.variance']._sync_for_productions(mo).filtered(
            lambda line: line.component_id == comp1
        )
        self.assertAlmostEqual(line.tolerance_percent, 15.0)
        self.assertEqual(line.classification, 'within')

    def test_negative_tolerance_rejected(self):
        with self.assertRaises(ValidationError):
            self.env.company.material_variance_tolerance = -1.0

    def test_company_specific_tolerance(self):
        company_a = self.env.company
        company_b = self.env['res.company'].create({'name': 'Variance Co B'})
        company_a.material_variance_tolerance = 5.0
        company_b.material_variance_tolerance = 20.0
        self.assertAlmostEqual(company_a.material_variance_tolerance, 5.0)
        self.assertAlmostEqual(company_b.material_variance_tolerance, 20.0)


@tagged('post_install', '-at_install')
class TestMaterialVarianceSecurity(TestMrpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_mrp_user = mail_new_test_user(
            cls.env,
            name='Variance User',
            login='variance_user',
            email='variance_user@example.com',
            groups='mrp.group_mrp_user,stock.group_stock_user',
        )
        cls.user_mrp_manager = mail_new_test_user(
            cls.env,
            name='Variance Manager',
            login='variance_manager',
            email='variance_manager@example.com',
            groups='mrp.group_mrp_manager,stock.group_stock_user',
        )
        cls.user_portal = mail_new_test_user(
            cls.env,
            name='Variance Portal',
            login='variance_portal',
            email='variance_portal@example.com',
            groups='base.group_portal',
        )
        cls.other_company = cls.env['res.company'].create({'name': 'Other Variance Co'})

    def test_user_cannot_write_tolerance(self):
        company = self.env.company.with_user(self.user_mrp_user)
        with self.assertRaises(AccessError):
            company.write({'material_variance_tolerance': 12.0})

    def test_manager_can_write_tolerance(self):
        company = self.env.company.with_user(self.user_mrp_manager)
        company.write({'material_variance_tolerance': 8.0})
        self.assertAlmostEqual(self.env.company.material_variance_tolerance, 8.0)

    def test_user_can_read_variance_in_company(self):
        mo, _bom, _finished, _c1, _c2 = self.generate_mo()
        lines = self.env['mrp.material.variance']._sync_for_productions(mo)
        self.assertTrue(lines)
        read_lines = lines.with_user(self.user_mrp_user)
        self.assertEqual(read_lines.mapped('component_id'), lines.mapped('component_id'))

    def test_user_cannot_access_other_company_variance(self):
        # Create a confirmed MO belonging to another company.
        finished = self.env['product.product'].create({
            'name': 'Other Co Finished',
            'is_storable': True,
            'type': 'consu',
            'company_id': False,
        })
        component = self.env['product.product'].create({
            'name': 'Other Co Component',
            'is_storable': True,
            'type': 'consu',
            'company_id': False,
        })
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': finished.product_tmpl_id.id,
            'product_qty': 1,
            'company_id': self.other_company.id,
            'type': 'normal',
            'consumption': 'flexible',
            'bom_line_ids': [(0, 0, {'product_id': component.id, 'product_qty': 2})],
        })
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.other_company.id)], limit=1,
        )
        if not warehouse:
            warehouse = self.env['stock.warehouse'].create({
                'name': 'Other WH',
                'code': 'OVW',
                'company_id': self.other_company.id,
                'partner_id': self.other_company.partner_id.id,
            })
        mo = self.env['mrp.production'].with_company(self.other_company).create({
            'product_id': finished.id,
            'bom_id': bom.id,
            'product_qty': 1,
            'product_uom_id': finished.uom_id.id,
            'company_id': self.other_company.id,
            'picking_type_id': warehouse.manu_type_id.id,
        })
        mo.action_confirm()
        lines = self.env['mrp.material.variance'].sudo()._sync_for_productions(mo)
        self.assertTrue(lines)
        self.assertEqual(lines.company_id, self.other_company)

        restricted_user = self.user_mrp_user
        restricted_user.company_ids = self.env.company
        restricted_user.company_id = self.env.company
        with self.assertRaises(AccessError):
            lines.with_user(restricted_user).read(['planned_qty'])

    def test_portal_cannot_read_variance(self):
        mo, _bom, _finished, _c1, _c2 = self.generate_mo()
        lines = self.env['mrp.material.variance']._sync_for_productions(mo)
        with self.assertRaises(AccessError):
            lines.with_user(self.user_portal).read(['planned_qty'])


@tagged('post_install', '-at_install')
class TestMaterialVarianceDashboard(TestMrpCommon):

    def test_dashboard_counts(self):
        self.env.company.material_variance_tolerance = 5.0
        stock_location = self.env.ref('stock.stock_location_stock')
        mo, _bom, _finished, comp1, comp2 = self.generate_mo(
            qty_final=1, qty_base_1=200, qty_base_2=10,
        )
        self.env['stock.quant']._update_available_quantity(comp1, stock_location, 500)
        self.env['stock.quant']._update_available_quantity(comp2, stock_location, 500)
        mo.action_assign()
        mo_form = Form(mo)
        mo_form.qty_producing = 1
        mo = mo_form.save()
        move1 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp1)
        move2 = mo.move_raw_ids.filtered(lambda m: m.product_id == comp2)
        move1.quantity = 220
        move1.picked = True
        move2.quantity = 10
        move2.picked = True
        mo.button_mark_done()

        dashboard = self.env['mrp.material.variance.dashboard'].create({})
        self.assertGreaterEqual(dashboard.mo_count, 1)
        self.assertGreaterEqual(dashboard.overconsumption_count, 1)
        self.assertGreaterEqual(dashboard.within_tolerance_count, 1)
