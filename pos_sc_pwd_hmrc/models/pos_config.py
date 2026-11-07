from odoo import api, fields, models, _
from odoo.exceptions import UserError
from pytz import timezone as pytz_timezone
import datetime
import logging
_logger = logging.getLogger(__name__)

class PosConfig(models.Model):
    _inherit = "pos.config"

    order_sequence_id = fields.Many2one(
        'ir.sequence',
        string='POS Order Sequence',
        help="Auto-created sequence used for pos.order names for this POS configuration."
    )

    return_order_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Return POS Order Sequence',
        help="Auto-created sequence used for return pos.order names for this POS configuration."
    )

    void_order_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Void POS Order Sequence',
        help="Auto-created sequence used for void pos.order names for this POS configuration."
    )


    transaction_sequence_id = fields.Many2one(
        'ir.sequence',
        string='Transaction Number Sequence',
        help="Auto-created sequence used for transaction numbers for this POS configuration."
    )

    hide_company_logo = fields.Boolean(
        string="Hide Company Logo on Receipts",
        default=True
    )

    branch_name = fields.Char(string="Branch Name")
    name_software = fields.Char(string=" Software Name ")
    version_software = fields.Char(string="Version No", )
    permit_no = fields.Char(string="Permit Number")
    no_release = fields.Char(string="Release number")
    release_date = fields.Date(string="Release Date")

    sequence_prefix_counter = fields.Integer(
        string="Sequence Prefix Counter",
        default=0,
        help="2-digit counter that increments when main sequence reaches 99999999"
    )


    transaction_prefix_counter = fields.Integer(
        string="Transaction Prefix Counter",
        default=0,
        help="2-digit counter that increments when transaction sequence reaches 99999999"
    )

    def _compute_last_session(self):
        for pos_config in self:
            session = self.env['pos.session'].search_read(
                [('config_id', '=', pos_config.id), ('state', '=', 'closed')],
                ['cash_register_balance_end_real', 'stop_at'],
                order='stop_at desc',
                limit=1,
            )
            if session:
                stop_at = session[0].get('stop_at')
                # ✅ Fix: stop_at False/bool check
                if stop_at and isinstance(stop_at, datetime.datetime):
                    tz = self.env.user.tz or 'UTC'
                    user_tz = pytz_timezone(tz)
                    pos_config.last_session_closing_date = stop_at.astimezone(user_tz).date()
                else:
                    pos_config.last_session_closing_date = False
                pos_config.last_session_closing_cash = session[0]['cash_register_balance_end_real']
            else:
                pos_config.last_session_closing_date = False
                pos_config.last_session_closing_cash = 0

    @api.model
    def default_get(self, fields_list):
        """Override default_get to set default sequence on record creation"""
        defaults = super().default_get(fields_list)

        if 'order_sequence_id' in fields_list and not defaults.get('order_sequence_id'):
            # Create sequence with temporary values
            config_name = defaults.get('name', 'New POS Config')
            sequence = self._create_default_sequence(config_name)
            defaults['order_sequence_id'] = sequence.id

        if 'return_order_sequence_id' in fields_list and not defaults.get('return_order_sequence_id'):
            # Create sequence with temporary values
            config_name = defaults.get('name', 'New POS Config')
            sequence = self._create_default_sequence(config_name, 'RET-')
            defaults['return_order_sequence_id'] = sequence.id

        if 'void_order_sequence_id' in fields_list and not defaults.get('void_order_sequence_id'):
            # Create sequence with temporary values
            config_name = defaults.get('name', 'New POS Config')
            sequence = self._create_default_sequence(config_name, 'VOID-')
            defaults['void_order_sequence_id'] = sequence.id


        if 'transaction_sequence_id' in fields_list and not defaults.get('transaction_sequence_id'):
            config_name = defaults.get('name', 'New POS Config')
            sequence = self._create_default_sequence(config_name, 'TXN-')
            defaults['transaction_sequence_id'] = sequence.id

        return defaults

    def _create_default_sequence(self, config_name, prefix=''):
        """Create a default sequence for the POS configuration"""
        seq_vals = {
            'name': f"{prefix} POS Orders - {config_name}",
            'code': f'pos.global.temp.{self.env["ir.sequence"]._get_number_next_actual()}',
            'padding': 8,
            'company_id': self.env.company.id,
            'use_date_range': False,
            'x_auto_created_by_pos_config': True,
            'prefix': prefix,
        }
        return self.env['ir.sequence'].sudo().create(seq_vals)

    def _get_formatted_sequence_number(self, sequence_type='order'):
        self.ensure_one()

        if sequence_type == 'return':
            sequence = self.return_order_sequence_id
        elif sequence_type == 'void':
            sequence = self.void_order_sequence_id
        else:
            sequence = self.order_sequence_id

        if not sequence:
            raise UserError(_("Sequence not configured for this POS."))

        current_number = sequence.number_next_actual

        # Check: Agar 99999999 cross kar gaya
        if current_number > 99999999:
            new_prefix_counter = self.sequence_prefix_counter + 1

            if new_prefix_counter > 99:
                raise UserError(_(
                    "Maximum sequence limit reached! "
                    "Prefix counter cannot exceed 99. "
                    "Please contact administrator."
                ))

            self.write({'sequence_prefix_counter': new_prefix_counter})

            sequence.sudo().write({'number_next_actual': 1})
            current_number = 1

            _logger.info(
                f"POS Config {self.id}: Invoice sequence rolled over. "
                f"Prefix counter incremented to {new_prefix_counter:02d}"
            )

        formatted_number = f"{self.sequence_prefix_counter:02d}-{current_number:08d}"
        sequence._next()

        return formatted_number


    def _get_formatted_transaction_number(self):

        self.ensure_one()

        sequence = self.transaction_sequence_id

        if not sequence:
            raise UserError(_("Transaction sequence not configured for this POS."))

        current_number = sequence.number_next_actual

        if current_number > 99999999:
            new_prefix_counter = self.transaction_prefix_counter + 1

            if new_prefix_counter > 99:
                raise UserError(_(
                    "Maximum transaction sequence limit reached! "
                    "Prefix counter cannot exceed 99. "
                    "Please contact administrator."
                ))

            self.write({'transaction_prefix_counter': new_prefix_counter})
            sequence.sudo().write({'number_next_actual': 1})
            current_number = 1

            _logger.info(
                f"POS Config {self.id}: Transaction sequence rolled over. "
                f"Prefix counter incremented to {new_prefix_counter:02d}"
            )

        formatted_number = f"{self.transaction_prefix_counter:02d}-{current_number:08d}"
        sequence._next()

        return formatted_number

    @api.model
    def create(self, vals):
        config = super().create(vals)

        # Update sequence with proper config ID and code
        if (config.order_sequence_id and
                config.order_sequence_id.x_auto_created_by_pos_config):
            config.order_sequence_id.sudo().write({
                'name': f"POS Orders - {config.name} (Config #{config.id})",
                'code': f'pos.global.sequence.{config.id}'
            })

        # Update return sequence
        if (config.return_order_sequence_id and
                config.return_order_sequence_id.x_auto_created_by_pos_config):
            config.return_order_sequence_id.sudo().write({
                'name': f"POS Return Orders - {config.name} (Config #{config.id})",
                'code': f'pos.global.return.sequence.{config.id}'
            })

        # Update void sequence
        if (config.void_order_sequence_id and
                config.void_order_sequence_id.x_auto_created_by_pos_config):
            config.void_order_sequence_id.sudo().write({
                'name': f"POS Void Orders - {config.name} (Config #{config.id})",
                'code': f'pos.global.void.sequence.{config.id}'
            })

        if (config.transaction_sequence_id and
                config.transaction_sequence_id.x_auto_created_by_pos_config):
            config.transaction_sequence_id.sudo().write({
                'name': f"POS Transactions - {config.name} (Config #{config.id})",
                'code': f'pos.global.transaction.sequence.{config.id}'
            })

        return config

    def copy(self, default=None):
        default = dict(default or {})
        default['order_sequence_id'] = False
        default['return_order_sequence_id'] = False
        default['void_order_sequence_id'] = False
        default['transaction_sequence_id'] = False  # NEW
        default['sequence_prefix_counter'] = 0
        default['transaction_prefix_counter'] = 0  # NEW
        return super().copy(default=default)

    def unlink(self):
        seqs_to_unlink = self.mapped('order_sequence_id').filtered(
            lambda s: s.x_auto_created_by_pos_config
        )
        return_seqs_to_unlink = self.mapped('return_order_sequence_id').filtered(
            lambda s: s.x_auto_created_by_pos_config
        )
        void_seqs_to_unlink = self.mapped('void_order_sequence_id').filtered(
            lambda s: s.x_auto_created_by_pos_config
        )

        transaction_seqs_to_unlink = self.mapped('transaction_sequence_id').filtered(
            lambda s: s.x_auto_created_by_pos_config
        )

        result = super().unlink()

        if seqs_to_unlink or return_seqs_to_unlink or void_seqs_to_unlink or transaction_seqs_to_unlink:
            try:
                seqs_to_unlink.sudo().unlink()
                return_seqs_to_unlink.sudo().unlink()
                void_seqs_to_unlink.sudo().unlink()
                transaction_seqs_to_unlink.sudo().unlink()  # NEW
            except Exception:
                pass

        return result

    @api.model
    def _setup_existing_configs(self):
        """Called during module installation to setup sequences for existing configs"""
        existing_configs = self.search([
            '|', '|', '|',
            ('order_sequence_id', '=', False),
            ('return_order_sequence_id', '=', False),
            ('void_order_sequence_id', '=', False),
            ('transaction_sequence_id', '=', False)  # NEW
        ])

        for config in existing_configs:
            if not config.order_sequence_id:
                seq = self._create_default_sequence(config.name)
                seq.sudo().write({
                    'name': f"POS Orders - {config.name} (Config #{config.id})",
                    'code': f'pos.global.sequence.{config.id}'
                })
                config.write({'order_sequence_id': seq.id})

        for config in existing_configs:
            if not config.return_order_sequence_id:
                seq = self._create_default_sequence(config.name, 'RET-')
                seq.sudo().write({
                    'name': f"POS Return Orders - {config.name} (Config #{config.id})",
                    'code': f'pos.global.return.sequence.{config.id}'
                })
                config.write({'return_order_sequence_id': seq.id})

        for config in existing_configs:
            if not config.void_order_sequence_id:
                seq = self._create_default_sequence(config.name, 'VOID-')
                seq.sudo().write({
                    'name': f"POS Void Orders - {config.name} (Config #{config.id})",
                    'code': f'pos.global.void.sequence.{config.id}'
                })
                config.write({'void_order_sequence_id': seq.id})


        for config in existing_configs:
            if not config.transaction_sequence_id:
                seq = self._create_default_sequence(config.name, 'TXN-')
                seq.sudo().write({
                    'name': f"POS Transactions - {config.name} (Config #{config.id})",
                    'code': f'pos.global.transaction.sequence.{config.id}'
                })
                config.write({'transaction_sequence_id': seq.id})


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    x_auto_created_by_pos_config = fields.Boolean(
        string="Auto-created by POS config",
        default=False
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_order_sequence_id = fields.Many2one(
        related="pos_config_id.order_sequence_id",
        readonly=False
    )
    pos_return_order_sequence_id = fields.Many2one(
        related="pos_config_id.return_order_sequence_id",
        readonly=False
    )
    pos_void_order_sequence_id = fields.Many2one(
        related="pos_config_id.void_order_sequence_id",
        readonly=False
    )

    pos_transaction_sequence_id = fields.Many2one(
        related="pos_config_id.transaction_sequence_id",
        readonly=False
    )

    pos_hide_company_logo = fields.Boolean(
        related="pos_config_id.hide_company_logo",
        readonly=False
    )
    branch = fields.Char(related="pos_config_id.branch_name", readonly=False)
    permit_number = fields.Char(related="pos_config_id.permit_no", readonly=False)
    software_name = fields.Char(related="pos_config_id.name_software", readonly=False)
    software_version = fields.Char(related="pos_config_id.version_software", readonly=False)
    release_no = fields.Char(related="pos_config_id.no_release", readonly=False)
    date_release = fields.Date(related="pos_config_id.release_date", readonly=False)

    pos_sequence_prefix_counter = fields.Integer(
        related="pos_config_id.sequence_prefix_counter",
        readonly=True,
        string="Current Prefix Counter"
    )


    pos_transaction_prefix_counter = fields.Integer(
        related="pos_config_id.transaction_prefix_counter",
        readonly=True,
        string="Current Transaction Prefix Counter"
    )