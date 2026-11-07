{
    'name': 'Pos Voice Agent',
    'version': '1.1.17',
    'category': 'Point of Sale',
    'summary': "",
    'description': "",
    'depends': ['point_of_sale'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_agent/static/src/js/wake_word.js',
        ],
    },
    'currency': 'USD',
    'price': 999,
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
    'uninstall_hook': 'uninstall_hook',
}
