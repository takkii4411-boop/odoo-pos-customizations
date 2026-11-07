from . import models
from . import wizard

def uninstall_hook(env):
    """Clean up auto-created sequences on module uninstall"""
    try:
        sequences = env['ir.sequence'].search([
            ('x_auto_created_by_pos_config', '=', True)
        ])
        if sequences:
            sequences.unlink()
    except Exception:
        pass
