from odoo import api, fields, models
import logging
_logger = logging.getLogger(__name__)

class PosSession(models.Model):

    _inherit = 'pos.session'

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        result.append('pos.special.discount')
        return result

    def _loader_params_res_partner(self):
        vals = super()._loader_params_res_partner()
        vals['search_params']['fields'] += ['is_senior_person', 'senior_pwd_person', 'naac_id_no', 'sc_id_no','general_id_no',
                                            'pwd_id_no', 'spic_id_no', 'medal_id_no', 'spic_child_name',
                                            'spic_child_birth_date', 'spic_child_age','res_partner_business_style', 'discount_code' ]
        return vals

    #

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        fields = result['search_params']['fields']
        fields = list(set(fields + [
            'allowed_discount_types','supported_discount_ids', 'supported_discount_codes', 'id'
        ]))
        result['search_params']['fields'] = fields
        return result


    def _loader_params_pos_special_discount(self):
        return {
            'search_params': {
                'domain': [
                    ('is_enabled', '=', True),
                    ('company_id', '=', self.config_id.company_id.id)
                ],
                'fields': [
                    'name', 'discount_code', 'button_name', 'discount_rate',
                    'fiscal_position_id', 'on_line_text', 'sequence', 'is_enabled', 'vat_treatment', 'is_default_discount', 'primary_codes'
                ],
                'order': 'sequence, name',
            },
        }

    def _get_pos_ui_pos_special_discount(self, params):
        return self.env['pos.special.discount'].search_read(**params['search_params'])

    def action_pos_session_closing_control(self, balancing_account=False, amount_to_balance=0):
        return self.action_pos_session_close()

    def _close_session_action(self, amount_to_balance):

        _logger.info("POS Session: Bypassing close session wizard, closing directly.")

        default_account = self._get_balancing_account()

        # Directly close without wizard popup
        self.action_pos_session_close(
            balancing_account=default_account,
            amount_to_balance=amount_to_balance,
        )
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def close_session_from_ui(self, bank_payment_method_diffs_by_id=None):
        bank_payment_method_diffs_by_id = bank_payment_method_diffs_by_id or {}
        if isinstance(bank_payment_method_diffs_by_id, list):
            bank_payment_method_diffs_by_id = dict(bank_payment_method_diffs_by_id)

        try:
            self.action_pos_session_closing_control(
                bank_payment_method_diffs=bank_payment_method_diffs_by_id
            )
        except Exception:
            try:
                default_account = self._get_balancing_account()
                self.action_pos_session_close(
                    balancing_account=default_account,
                    amount_to_balance=0,
                )
            except Exception:
                pass

        return {'successful': True}

class AccountFiscalPosition(models.Model):
    _inherit = "account.fiscal.position"

    is_zero_exemption_vat = fields.Selection(string='Is Zero Rated/VAT Exempt', selection=[('zero_rated', 'ZERO-RATED SALE'), ('vat_exempt', 'VAT-Exempt')])
