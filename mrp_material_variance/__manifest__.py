# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing Material Variance Tracker',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Compare planned vs actual raw material consumption on manufacturing orders',
    'description': """
Manufacturing Material Variance Tracker
=======================================
Compare planned BoM/component demand against actual consumption on manufacturing
orders, classify variances against a company tolerance, and surface over- and
under-consumption for manufacturing managers.
    """,
    'author': 'Manufacturing Material Variance Tracker',
    'license': 'LGPL-3',
    'depends': ['mrp'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/material_variance_views.xml',
        'views/mrp_production_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
